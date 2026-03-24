"""
Агент на GigaChat с вызовом инструментов schema, query, explain.
Поддерживает пользовательские сессии, историю диалога и защищённую обработку.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from src.config import load_config
from src.logging_db import LoggingDB
from src.orchestrator import (
    SYSTEM_PROMPT_SYNTHESIS,
    SYSTEM_PROMPT_TOOLS,
    SYSTEM_PROMPT_WEB_SEARCH_APPEND,
    extract_entities,
    format_table_markdown,
)
from src.rag import search as rag_search
from src.security import PromptGuard
from src.sessions import SessionManager
from src.llm import chat_completion, chat_with_tools, get_gigachat_functions
from src.tools import tool_explain, tool_query, tool_schema
from src.web_search import is_web_search_enabled, web_search


def _normalize_sql_arg(sql: Any) -> str:
    """
    Приводит SQL-аргумент от function_call к исполнимому виду.
    Частый кейс: модель передаёт literal-экранирование ("\\n", "\\t"),
    и SQLite видит символ "\\" как токен. Убираем также оставшиеся одиночные
    обратные косые, чтобы избежать "unrecognized token".
    """
    if sql is None:
        return ""
    text = str(sql).strip()
    if not text:
        return ""

    if "\\n" in text or "\\t" in text or "\\r" in text:
        text = (
            text.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
        )
    # Удаляем оставшиеся одиночные \ (не входящие в \n, \t, \r), чтобы SQLite не падал
    text = re.sub(r"\\(?!n|t|r)", "", text)
    return text


def _build_synthesis_user_prompt(question: str, all_query_results: list[dict[str, Any]], max_queries: int = 5, max_rows: int = 30) -> str:
    selected = all_query_results[:max_queries]
    blocks: list[str] = []
    for i, item in enumerate(selected, start=1):
        sql = str(item.get("sql", "")).strip() or "SQL не определен"
        rows = item.get("rows", []) or []
        rows_limited = rows[:max_rows]
        table_md = format_table_markdown(rows_limited) if rows_limited else "_Нет строк._"
        blocks.append(
            f"Набор {i}\n"
            f"SQL:\n{sql}\n\n"
            f"Строк: {len(rows)}\n"
            f"Фрагмент (до {max_rows} строк):\n{table_md}\n"
        )
    return (
        f"Вопрос пользователя:\n{question}\n\n"
        f"Нужно объединить результаты нескольких SQL-запросов в один ответ.\n\n"
        f"{'-' * 24}\n"
        + "\n".join(blocks)
    )


def _looks_like_data_question(text: str) -> bool:
    if not (text and text.strip()):
        return False
    t = text.lower().strip()
    data_hints = (
        "регион", "област", "зарплат", "оплат", "труд", "мрот", "средн", "показател",
        "данные из базы", "по данным", "сравн", "выборк", "таблиц", "запрос к бд",
    )
    return any(h in t for h in data_hints)


def _suggests_need_db_access(text: str) -> bool:
    if not (text and text.strip()):
        return False
    t = text.lower()
    phrases = (
        "нужен доступ к бд", "доступ к базе", "уточните", "нужна база", "предоставьте доступ",
        "получить данные из базы", "необходимо получить", "мне необходимо получить",
        "нужно получить данные", "необходимы данные из",
    )
    return any(p in t for p in phrases)


def _usage_to_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "total_tokens": getattr(usage, "total_tokens", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def _serialize_response(response: Any) -> dict[str, Any]:
    try:
        choice = response.choices[0]
        msg = choice.message
        fc = getattr(msg, "function_call", None)
        data = {
            "finish_reason": getattr(choice, "finish_reason", None),
            "content": getattr(msg, "content", None),
            "function_call": {
                "name": getattr(fc, "name", None) if fc else None,
                "arguments": getattr(fc, "arguments", None) if fc else None,
            },
            "usage": _usage_to_dict(getattr(response, "usage", None)),
        }
        return data
    except Exception:
        return {"error": "serialize_response_failed"}


def _history_to_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history:
        role = item.get("role", "")
        content = item.get("content", "")
        if role in ("user", "assistant", "function") and content:
            payload: dict[str, str] = {"role": role, "content": content}
            if role == "function" and item.get("tool_name"):
                payload["name"] = str(item["tool_name"])
            messages.append(payload)
    return messages


def run_agent_with_tools(
    question: str,
    config: dict | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Агент с тулзами: GigaChat может вызывать schema, query, explain.
    """
    cfg = config or load_config()
    db_path = cfg["db_path"]
    chroma_path = cfg["chroma_path"]
    max_rows = cfg["max_rows"]
    timeout = cfg["query_timeout_sec"]
    creds = cfg.get("gigachat_credentials", "")
    desc_path = str(cfg.get("schema_descriptions_path", ""))
    session_manager = SessionManager(cfg["session_db_path"])
    logging_db = LoggingDB(cfg["logging_db_path"])
    guard = PromptGuard(max_input_length=cfg.get("max_input_length", 2000))

    result = {
        "ok": False,
        "session_id": "",
        "answer": "",
        "table_md": "",
        "rows": [],
        "explanation": "",
        "entities": {},
        "sql": "",
        "error": None,
        "row_count": 0,
        "elapsed_sec": 0,
        "tools_called": [],
        "all_query_results": [],
    }

    question = guard.sanitize_input(question)
    if not question or not question.strip():
        result["error"] = "Пустой вопрос"
        return result

    if guard.is_injection_attempt(question):
        safe_session_id = session_manager.ensure_session(session_id)
        result["session_id"] = safe_session_id
        text = guard.injection_reply()
        result["answer"] = text
        result["error"] = "Обнаружена попытка prompt-injection."
        logging_db.log_event(
            "security_blocked_prompt_injection",
            {"question": question[:500]},
            session_id=safe_session_id,
        )
        session_manager.add_message(safe_session_id, "user", question, visible_to_user=True)
        session_manager.add_message(
            safe_session_id,
            "assistant",
            text,
            visible_to_user=True,
            meta={"blocked": True},
        )
        return result

    safe_session_id = session_manager.ensure_session(session_id)
    result["session_id"] = safe_session_id
    session_manager.cleanup_expired(cfg.get("session_max_age_hours", 24))

    context = ""
    try:
        rag_result = rag_search(question, chroma_path, k_ddl=cfg.get("rag_k_ddl", 5), k_examples=cfg.get("rag_k_examples", 2))
        context = rag_result.get("context_for_prompt", "")
    except Exception as e:
        logging_db.log_event("rag_error", {"error": str(e)[:200]}, session_id=safe_session_id)

    web_search_enabled = is_web_search_enabled(cfg)
    functions = get_gigachat_functions(enable_web_search=web_search_enabled)
    if not functions:
        result["error"] = "Не удалось загрузить описания инструментов GigaChat."
        logging_db.log_event("tools_init_error", {"error": result["error"]}, session_id=safe_session_id)
        return result

    history_messages = _history_to_messages(
        session_manager.get_history(
            safe_session_id,
            include_hidden=True,
            max_messages=max(1, int(cfg.get("session_max_history_turns", 20)) * 4),
        )
    )
    user_content = f"Вопрос пользователя: {question}"
    if context:
        user_content = f"Контекст схемы (для справки):\n\n{context}\n\n---\n" + user_content

    system_prompt = SYSTEM_PROMPT_TOOLS
    if web_search_enabled:
        system_prompt = f"{SYSTEM_PROMPT_TOOLS}\n{SYSTEM_PROMPT_WEB_SEARCH_APPEND}"
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_content})

    session_manager.add_message(
        safe_session_id,
        "user",
        user_content,
        visible_to_user=True,
        meta={"raw_question": question},
    )
    logging_db.log_event("question", {"question": question[:500]}, session_id=safe_session_id)

    last_query_rows = []
    last_query_sql = ""
    all_query_results: list[dict[str, Any]] = []
    max_turns = 50
    final_content = ""
    force_tools_retry_used = False

    try:
        for turn in range(max_turns):
            t0 = time.perf_counter()
            response = chat_with_tools(
                messages,
                functions,
                credentials=creds,
                model=cfg.get("llm_model"),
                temperature=0.1,
                max_tokens=cfg.get("max_completion_tokens", 4096),
                verify_ssl_certs=cfg.get("gigachat_verify_ssl", False),
                timeout=float(cfg.get("gigachat_timeout_sec", 120)),
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            response_data = _serialize_response(response)
            usage = response_data.get("usage") if isinstance(response_data, dict) else None
            tokens_used = None
            if isinstance(usage, dict):
                tokens_used = usage.get("total_tokens")
            logging_db.log_llm_call(
                session_id=safe_session_id,
                model=cfg.get("llm_model"),
                request_messages=messages,
                response_data=response_data,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            choice = response.choices[0]
            msg = choice.message
            finish_reason = getattr(choice, "finish_reason", None)
            content = (msg.content or "").strip() if hasattr(msg, "content") else ""

            fc = getattr(msg, "function_call", None)
            if finish_reason == "function_call" and fc is not None:
                name = getattr(fc, "name", None) or getattr(fc, "name_", "")
                args_str = getattr(fc, "arguments", None) or getattr(fc, "arguments_", "") or "{}"
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}

                result["tools_called"].append(name)
                logging_db.log_event(
                    "tool_call",
                    {"tool": name, "turn": turn, "args": args},
                    session_id=safe_session_id,
                )
                tool_result = ""
                if name == "schema":
                    out = tool_schema(db_path, desc_path, format=args.get("format", "full"))
                    tool_result = out.get("schema", out.get("error", ""))
                elif name == "query":
                    sql = _normalize_sql_arg(args.get("sql", ""))
                    limit = args.get("limit") or max_rows
                    timeout_sec = args.get("timeout_sec") or timeout
                    out = tool_query(db_path, sql, max_rows=limit, timeout_sec=float(timeout_sec), validate=True)
                    if out.get("ok"):
                        rows = out.get("rows", [])
                        last_query_rows = rows
                        last_query_sql = sql
                        all_query_results.append(
                            {
                                "sql": sql,
                                "rows": rows,
                                "row_count": len(rows),
                            }
                        )
                        if not rows:
                            tool_result = "Строк: 0."
                        else:
                            keys = list(rows[0].keys())
                            tool_result = "\n".join(["\t".join(keys)] + ["\t".join(str(r.get(k, "")) for k in keys) for r in rows])
                    else:
                        tool_result = out.get("error", "Ошибка")
                elif name == "explain":
                    sql = _normalize_sql_arg(args.get("sql", ""))
                    out = tool_explain(db_path, sql)
                    tool_result = out.get("plan", "") or out.get("syntax_error", "") or out.get("error", "")
                    if isinstance(tool_result, str) and "unrecognized token" in tool_result.lower():
                        tool_result = (
                            "Ошибка EXPLAIN: unrecognized token \"\\\\\". "
                            "Передай SQL без literal-экранирования (используй реальные переводы строк вместо \\n) "
                            "или сразу вызови query с корректным SELECT."
                        )
                elif name == "web_search":
                    if not web_search_enabled:
                        tool_result = "Инструмент web_search выключен."
                    else:
                        try:
                            max_results = int(args.get("max_results") or 5)
                        except (TypeError, ValueError):
                            max_results = 5
                        out = web_search(
                            args.get("query", ""),
                            max_results=max(1, min(max_results, 10)),
                            config=cfg,
                        )
                        if out.get("ok"):
                            items = out.get("results", [])
                            if not items:
                                tool_result = "Результатов не найдено."
                            else:
                                lines = []
                                for i, item in enumerate(items, start=1):
                                    title = str(item.get("title", "")).strip() or "Без названия"
                                    url = str(item.get("url", "")).strip() or "-"
                                    snippet = str(item.get("snippet", "")).strip() or "Описание отсутствует."
                                    lines.append(f"{i}. {title}\nURL: {url}\n{snippet}")
                                tool_result = "\n\n".join(lines)
                        else:
                            tool_result = out.get("error", "Поиск временно недоступен.")
                else:
                    tool_result = f"Неизвестный инструмент: {name}"

                assistant_tool_msg = content or "(вызов инструмента)"
                messages.append({"role": "assistant", "content": assistant_tool_msg})
                messages.append({"role": "function", "name": name, "content": tool_result})
                session_manager.add_message(
                    safe_session_id,
                    "assistant",
                    assistant_tool_msg,
                    visible_to_user=False,
                    meta={"tool_call": name},
                )
                session_manager.add_message(
                    safe_session_id,
                    "function",
                    tool_result,
                    visible_to_user=False,
                    tool_name=name,
                    meta={"turn": turn},
                )
                continue
            else:
                final_content = guard.sanitize_output(content)
                if (
                    not force_tools_retry_used
                    and not last_query_rows
                    and "query" not in result["tools_called"]
                    and _looks_like_data_question(question)
                    and _suggests_need_db_access(final_content or "")
                ):
                    force_tools_retry_used = True
                    force_msg = (
                        "Обязательно ответь вызовами инструментов: сначала schema, затем query. "
                        "Не предлагай доступ к БД — используй имеющиеся инструменты. Вопрос по данным повторён для выполнения запроса."
                    )
                    messages.append({"role": "assistant", "content": final_content or "(ответ без вызова инструментов)"})
                    messages.append({"role": "user", "content": force_msg})
                    logging_db.log_event(
                        "agent_retry_force_tools",
                        {"reason": "data_question_answered_without_query"},
                        session_id=safe_session_id,
                    )
                    continue
                break
        else:
            if guard.is_internal_reasoning_leak(content):
                final_content = guard.sanitize_output(
                    "Достигнут лимит шагов. Не удалось получить результат запроса. Попробуйте переформулировать запрос."
                )
            else:
                final_content = guard.sanitize_output(content or "Достигнут лимит шагов.")
    except RuntimeError as e:
        result["error"] = str(e)
        logging_db.log_event("agent_runtime_error", {"error": result["error"][:500]}, session_id=safe_session_id)
        return result

    result["all_query_results"] = all_query_results
    synthesis_answer = ""
    if len(all_query_results) >= 2:
        synthesis_prompt = _build_synthesis_user_prompt(question, all_query_results)
        try:
            synthesis_answer = chat_completion(
                [
                    {"role": "system", "content": SYSTEM_PROMPT_SYNTHESIS},
                    {"role": "user", "content": synthesis_prompt},
                ],
                credentials=cfg.get("gigachat_credentials"),
                model=cfg.get("llm_model"),
                temperature=0.1,
                max_tokens=cfg.get("max_completion_tokens", 4096),
                verify_ssl_certs=cfg.get("gigachat_verify_ssl", False),
                timeout=float(cfg.get("gigachat_timeout_sec", 120)),
            )
            synthesis_answer = (synthesis_answer or "").strip()
        except RuntimeError as e:
            logging_db.log_event("synthesis_error", {"error": str(e)[:500]}, session_id=safe_session_id)
            synthesis_answer = (
                "Не удалось объединить результаты нескольких запросов автоматически. "
                "Ниже показан ответ по последнему успешному запросу."
            )

    if last_query_rows:
        result["rows"] = last_query_rows
        result["table_md"] = format_table_markdown(last_query_rows)
        result["row_count"] = len(last_query_rows)
        result["sql"] = last_query_sql
        result["entities"] = extract_entities(last_query_sql)
        result["explanation"] = f"Выполнен запрос, возвращено строк: {len(last_query_rows)}. Таблицы: {', '.join(result['entities'].get('tables', []))}."
        fc_lower = (final_content or "").lower()
        search_unavailable = (
            "недоступен" in fc_lower
            and ("поиск" in fc_lower or "сервис" in fc_lower or "интернет" in fc_lower)
        )
        if search_unavailable and web_search_enabled:
            note = "Внешние данные (например МРОТ) в БД отсутствуют; для сравнения нужен веб-поиск — он временно недоступен. Ниже данные из БД."
            result["answer"] = guard.sanitize_output(
                f"{result['explanation']}\n\n**Результат:**\n\n{result['table_md']}\n\n{note}"
            )
        else:
            result["answer"] = guard.sanitize_output(
                f"{result['explanation']}\n\n**Результат:**\n\n{result['table_md']}\n\n**Ответ модели:** {final_content}"
            )
    else:
        if guard.is_internal_reasoning_leak(final_content):
            result["answer"] = guard.sanitize_output(
                "По запросу данных не найдено. Попробуйте переформулировать вопрос или уточнить регион/период."
            )
        else:
            result["answer"] = guard.sanitize_output(final_content or "Нет результата.")

    if synthesis_answer:
        tables_parts = []
        for i, item in enumerate(all_query_results, 1):
            rows = item.get("rows") or []
            if rows:
                tables_parts.append(f"Набор {i}:\n{format_table_markdown(rows)}")
        tables_block = "\n\n".join(tables_parts) if tables_parts else ""
        if tables_block:
            result["answer"] = guard.sanitize_output(
                f"**Результаты запросов:**\n\n{tables_block}\n\n**Ответ модели:** {synthesis_answer}"
            )
        else:
            result["answer"] = guard.sanitize_output(synthesis_answer)

    result["ok"] = True
    session_manager.add_message(
        safe_session_id,
        "assistant",
        result["answer"],
        visible_to_user=True,
        meta={"row_count": result.get("row_count", 0), "sql": result.get("sql", "")},
    )
    logging_db.log_event("answer", {"row_count": result.get("row_count", 0)}, session_id=safe_session_id)
    logging_db.log_user_interaction(
        session_id=safe_session_id,
        question=question,
        answer=result["answer"],
        sql_generated=result.get("sql", ""),
        row_count=result.get("row_count", 0),
        tools_used=result.get("tools_called", []),
    )
    return result
