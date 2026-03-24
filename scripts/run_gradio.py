#!/usr/bin/env python3
"""
Gradio-интерфейс как тонкий клиент к API. Не дублирует движок — все запросы идут в API.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gradio as gr

# URL API (тот же бэкенд, без дублирования моделей и логики)
API_BASE = os.environ.get("SQL_AGENT_API_URL", "http://127.0.0.1:8000")

MODE_BY_LABEL: dict[str, Literal["chat", "excel", "report"]] = {
    "Чат": "chat",
    "Выгрузка в Excel": "excel",
    "Отчёт": "report",
}


def _api_post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(download_url: str) -> str | None:
    """Скачивает файл по download_url и возвращает путь к временному файлу."""
    if not download_url:
        return None
    try:
        url = f"{API_BASE}{download_url}" if download_url.startswith("/") else download_url
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read()
        name = Path(download_url).name or "download"
        fd, path = tempfile.mkstemp(suffix=name)
        os.write(fd, raw)
        os.close(fd)
        return path
    except Exception:
        return None


def _to_messages(history: list) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict) and "role" in item and "content" in item:
            out.append({"role": item["role"], "content": item["content"]})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            u, a = item[0], item[1]
            if u:
                out.append({"role": "user", "content": str(u)})
            if a:
                out.append({"role": "assistant", "content": str(a)})
    return out


def chat_fn(
    message: str,
    history: list,
    show_sql: bool,
    mode_label: str,
    session_id: str,
) -> tuple[list[dict[str, str]], str, str, Any]:
    """Отправляет запрос в API, без локального движка."""
    messages = _to_messages(history)
    if not message or not message.strip():
        messages.append({"role": "assistant", "content": "Пожалуйста, введите вопрос."})
        return messages, session_id or "", "", gr.update(value=None, visible=False)

    mode = MODE_BY_LABEL.get(mode_label, "chat")
    try:
        r = _api_post(
            "/api/chat",
            {
                "message": message.strip(),
                "session_id": session_id or None,
                "show_sql": show_sql,
                "mode": mode,
            },
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        messages.append({"role": "user", "content": message.strip()})
        messages.append({"role": "assistant", "content": f"**Ошибка API ({e.code}):** {body[:500]}"})
        return messages, session_id or "", "", gr.update(value=None, visible=False)
    except OSError as e:
        messages.append({"role": "user", "content": message.strip()})
        messages.append({"role": "assistant", "content": f"**Не удалось подключиться к API.** Запущен ли сервер на {API_BASE}? Ошибка: {e}"})
        return messages, session_id or "", "", gr.update(value=None, visible=False)

    sid = r.get("session_id", session_id)
    answer = r.get("answer", "Нет ответа.")
    # Чтобы инлайн-ссылка «Скачать отчёт (PDF)» открывалась в браузере, подставляем абсолютный URL API
    if r.get("download_url"):
        base = API_BASE.rstrip("/")
        rel = r["download_url"]
        abs_url = f"{base}{rel}" if rel.startswith("/") else rel
        answer = answer.replace(f"]({rel})", f"]({abs_url})")
    messages.append({"role": "user", "content": message.strip()})
    messages.append({"role": "assistant", "content": answer})

    file_path: str | None = None
    if r.get("download_url"):
        file_path = _download_file(r["download_url"])
    file_update = gr.update(value=file_path, visible=bool(file_path)) if file_path else gr.update(value=None, visible=False)
    return messages, sid, "", file_update


def clear_context(session_id: str) -> tuple[list[dict[str, str]], str, Any]:
    """Очистка контекста через API."""
    if not session_id:
        return [{"role": "assistant", "content": "Контекст очищен. Можете начать новый разговор."}], "", gr.update(value=None, visible=False)
    try:
        r = _api_post("/api/clear", {"session_id": session_id})
        sid = r.get("session_id", session_id)
    except Exception:
        sid = session_id
    msg = "Контекст диалога очищен. Можете начать новый разговор."
    return [{"role": "assistant", "content": msg}], sid, gr.update(value=None, visible=False)


def build_app() -> gr.Blocks:
    favicon_path = ROOT / "frontend" / "favicon.png"
    try:
        blocks_kw: dict[str, Any] = {"title": "SQL Agent"}
        if favicon_path.exists():
            blocks_kw["favicon_path"] = str(favicon_path)
        app_ctx = gr.Blocks(**blocks_kw)
    except TypeError:
        app_ctx = gr.Blocks(title="SQL Agent")
    with app_ctx as app:
        gr.Markdown("## ИИ-агент по данным муниципальных образований")

        session_id = gr.State("")
        show_sql = gr.Checkbox(label="Показывать SQL-запрос", value=False, interactive=True)
        mode = gr.Dropdown(
            label="Режим",
            choices=["Чат", "Выгрузка в Excel", "Отчёт"],
            value="Чат",
            interactive=True,
        )

        chatbot = gr.Chatbot(label="Диалог", height=520)
        download_file = gr.File(label="Скачать файл (Excel или PDF)", visible=False)
        with gr.Row():
            msg = gr.Textbox(
                label="Ваш вопрос",
                placeholder="Например: Сколько записей в таблице consumption?",
                lines=2,
                scale=8,
            )
            with gr.Column(scale=1, min_width=180):
                send_btn = gr.Button("Отправить", variant="primary")
                clear_btn = gr.Button("Очистить контекст", variant="secondary")

        send_btn.click(
            fn=chat_fn,
            inputs=[msg, chatbot, show_sql, mode, session_id],
            outputs=[chatbot, session_id, msg, download_file],
        )
        msg.submit(
            fn=chat_fn,
            inputs=[msg, chatbot, show_sql, mode, session_id],
            outputs=[chatbot, session_id, msg, download_file],
        )
        clear_btn.click(
            fn=clear_context,
            inputs=[session_id],
            outputs=[chatbot, session_id, download_file],
        )

    return app


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", theme=gr.themes.Soft())
