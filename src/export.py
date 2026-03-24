"""
Экспорт результатов в Excel, генерация аналитического отчёта и выгрузка отчёта в PDF.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import markdown
from openpyxl import Workbook

from src.llm import chat_completion
from src.orchestrator import (
    SYSTEM_PROMPT_REPORT,
    SYSTEM_PROMPT_REPORT_MULTI_QUERY_APPEND,
    format_table_markdown,
)


def export_report_to_pdf(
    report_text: str,
    *,
    export_dir: str | Path = "data/exports",
    filename_prefix: str = "report",
) -> Path:
    """Конвертирует текст отчёта (markdown) в PDF и возвращает путь к файлу."""
    export_path = Path(export_dir)
    if not export_path.is_absolute():
        export_path = Path(__file__).resolve().parent.parent / export_path
    export_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    filename = f"{filename_prefix}_{ts}_{suffix}.pdf"
    file_path = export_path / filename

    html_body = markdown.markdown(
        report_text or "Нет содержимого.",
        extensions=["extra", "nl2br"],
        output_format="html5",
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <style>
    body {{ font-family: Georgia, serif; padding: 2em; line-height: 1.5; color: #222; }}
    h1, h2, h3 {{ margin-top: 1em; }}
    table {{ border-collapse: collapse; margin: 1em 0; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
    th {{ background: #f0f0f0; }}
    code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }}
    pre {{ background: #f5f5f5; padding: 1em; overflow-x: auto; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""
    from weasyprint import HTML
    HTML(string=html_doc).write_pdf(file_path)
    return file_path


def export_to_excel(
    rows: list[dict[str, Any]],
    *,
    export_dir: str | Path = "data/exports",
    filename_prefix: str = "query_result",
) -> Path:
    """Сохраняет список словарей в xlsx и возвращает путь к файлу."""
    export_path = Path(export_dir)
    if not export_path.is_absolute():
        export_path = Path(__file__).resolve().parent.parent / export_path
    export_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    filename = f"{filename_prefix}_{ts}_{suffix}.xlsx"
    file_path = export_path / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"

    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])
    else:
        ws.append(["message"])
        ws.append(["Нет данных для выгрузки"])

    wb.save(file_path)
    return file_path


def generate_report(
    *,
    question: str,
    rows: list[dict[str, Any]],
    sql: str,
    config: dict[str, Any],
    all_query_results: list[dict[str, Any]] | None = None,
) -> str:
    """Генерирует подробный отчёт по результатам запроса через LLM."""
    all_results = all_query_results or []
    report_system_prompt = SYSTEM_PROMPT_REPORT
    if len(all_results) >= 2:
        report_system_prompt = f"{SYSTEM_PROMPT_REPORT}\n{SYSTEM_PROMPT_REPORT_MULTI_QUERY_APPEND}"
        blocks: list[str] = []
        for i, item in enumerate(all_results[:5], start=1):
            item_sql = str(item.get("sql", "")).strip() or "Не определен"
            item_rows = item.get("rows", []) or []
            table_md = format_table_markdown(item_rows[:50]) if item_rows else "_Нет строк для анализа._"
            blocks.append(
                f"Набор данных {i}\n"
                f"SQL:\n{item_sql}\n\n"
                f"Количество строк: {len(item_rows)}\n\n"
                f"Фрагмент данных (до 50 строк):\n{table_md}\n"
            )
        user_prompt = (
            f"Вопрос пользователя:\n{question}\n\n"
            "Подготовь максимально подробный и точный интерпретационный отчет по всем наборам данных ниже.\n\n"
            f"{'-' * 24}\n"
            + "\n".join(blocks)
        )
    else:
        table_md = format_table_markdown(rows) if rows else "_Нет строк для анализа._"
        user_prompt = (
            f"Вопрос пользователя:\n{question}\n\n"
            f"SQL-запрос:\n{sql or 'Не определен'}\n\n"
            f"Количество строк в результате: {len(rows)}\n\n"
            f"Фрагмент данных (до 50 строк):\n{table_md}\n\n"
            "Подготовь максимально подробный и точный интерпретационный"
            " отчет по этим данным, учитывая пожелания пользователя.\n"
            "Отчет должен быть на русском языке, основываться на данных. Стиль - формальный."
        )

    text = chat_completion(
        [
            {"role": "system", "content": report_system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        credentials=config.get("gigachat_credentials"),
        model=config.get("llm_model"),
        temperature=0.2,
        max_tokens=2048,
        verify_ssl_certs=config.get("gigachat_verify_ssl", False),
        timeout=float(config.get("gigachat_timeout_sec", 120)),
    )
    return (text or "").strip()
