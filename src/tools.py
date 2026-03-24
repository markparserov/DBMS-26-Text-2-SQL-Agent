"""
Инструменты для работы с БД: schema, query, explain.
Используются оркестратором и могут быть обёрнуты в MCP-сервер.
"""
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from src.rag.schema import get_ddl_from_sqlite, load_schema_descriptions
from src.rag.chunks import build_ddl_chunks
from src.sql_validator import validate_and_prepare


def _sanitize_db_error(error: Exception) -> dict[str, str]:
    """
    Приводит ошибку БД к безопасному и полезному для модели виду.
    Не возвращает пути к файлам и внутренние технические детали.
    """
    raw = str(error or "").strip()
    # Убираем пути и лишние переносы строк
    cleaned = re.sub(r"(?:[A-Za-z]:)?/[^\s:]+", "[path]", raw)
    cleaned = " ".join(cleaned.split())
    low = cleaned.lower()

    if "no such table" in low:
        return {
            "error_type": "no_such_table",
            "message": cleaned,
            "hint": "Проверь имена таблиц через schema.",
        }
    if "no such column" in low:
        return {
            "error_type": "no_such_column",
            "message": cleaned,
            "hint": "Проверь имена колонок через schema.",
        }
    if "ambiguous column name" in low:
        return {
            "error_type": "ambiguous_column",
            "message": cleaned,
            "hint": "Укажи алиасы таблиц и префиксы колонок.",
        }
    if "syntax error" in low or low.startswith("near "):
        return {
            "error_type": "syntax_error",
            "message": cleaned,
            "hint": "Проверь синтаксис SELECT и соответствие диалекту SQLite.",
        }
    if "unrecognized token" in low:
        return {
            "error_type": "unrecognized_token",
            "message": cleaned,
            "hint": "Удали лишние экранирования и специальные символы.",
        }
    return {
        "error_type": "db_error",
        "message": "Ошибка БД при выполнении запроса.",
        "hint": "Проверь SQL и схему через schema/explain.",
    }


def tool_schema(
    db_path: str | Path,
    descriptions_path: str | Path | None = None,
    format: str = "full",
) -> dict[str, Any]:
    """
    Возвращает схему БД: DDL + комментарии к таблицам/колонкам.
    format: "full" | "compact" (compact — только имена таблиц и колонок).
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"ok": False, "error": f"База не найдена: {db_path}", "schema": ""}

    ddl_records = get_ddl_from_sqlite(db_path)
    descriptions = load_schema_descriptions(descriptions_path) if descriptions_path else {}
    chunks = build_ddl_chunks(ddl_records, descriptions)

    if format == "compact":
        lines = []
        for rec in ddl_records:
            cols = ", ".join(c.get("name", "") for c in rec.get("columns", []))
            lines.append(f"Таблица {rec['table']}: {cols}")
        schema_text = "\n".join(lines)
    else:
        schema_text = "\n\n".join(c["content"] for c in chunks)

    return {"ok": True, "schema": schema_text, "tables": [r["table"] for r in ddl_records]}


def tool_query(
    db_path: str | Path,
    sql: str,
    max_rows: int = 100,
    timeout_sec: float = 30.0,
    validate: bool = True,
) -> dict[str, Any]:
    """
    Выполняет запрос. Только SELECT; лимит и таймаут применяются.
    timeout_sec ограничивает время выполнения запроса (sqlite3.connect timeout — только ожидание блокировки).
    Возвращает: ok, rows, row_count, elapsed_sec, error; при таймауте — error_type query_timeout.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"ok": False, "error": "База не найдена", "rows": [], "row_count": 0, "elapsed_sec": 0}

    if validate:
        ok, err, prepared = validate_and_prepare(sql, max_rows)
        if not ok:
            return {"ok": False, "error": err, "rows": [], "row_count": 0, "elapsed_sec": 0}
        sql = prepared

    start = time.perf_counter()
    aborted_by_timeout = []
    progress_interval = 10000
    conn = None

    def _progress_handler() -> int:
        if time.perf_counter() - start >= timeout_sec:
            aborted_by_timeout.append(True)
            return 1
        return 0

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.set_progress_handler(_progress_handler, progress_interval)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        rows_raw = cur.fetchall()
        conn.set_progress_handler(None, progress_interval)
        conn.close()
    except sqlite3.OperationalError as e:
        if conn is not None:
            try:
                conn.set_progress_handler(None, progress_interval)
                conn.close()
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        if aborted_by_timeout:
            return {
                "ok": False,
                "error": (
                    f"Запрос отменён по таймауту ({timeout_sec} с). "
                    "Упростите запрос: меньше JOIN, добавьте фильтры по году/периоду или ограничьте выборку."
                ),
                "error_type": "query_timeout",
                "rows": [],
                "row_count": 0,
                "elapsed_sec": round(elapsed, 3),
            }
        err = _sanitize_db_error(e)
        return {
            "ok": False,
            "error": f"Ошибка SQL ({err['error_type']}): {err['message']}. {err['hint']}",
            "rows": [],
            "row_count": 0,
            "elapsed_sec": round(elapsed, 3),
        }
    except Exception as e:
        if conn is not None:
            try:
                conn.set_progress_handler(None, progress_interval)
                conn.close()
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        if aborted_by_timeout:
            return {
                "ok": False,
                "error": (
                    f"Запрос отменён по таймауту ({timeout_sec} с). "
                    "Упростите запрос: меньше JOIN, добавьте фильтры по году/периоду или ограничьте выборку."
                ),
                "error_type": "query_timeout",
                "rows": [],
                "row_count": 0,
                "elapsed_sec": round(elapsed, 3),
            }
        err = _sanitize_db_error(e)
        return {
            "ok": False,
            "error": f"Ошибка SQL ({err['error_type']}): {err['message']}. {err['hint']}",
            "rows": [],
            "row_count": 0,
            "elapsed_sec": round(elapsed, 3),
        }

    elapsed = time.perf_counter() - start
    rows = [dict(r) for r in rows_raw]
    return {
        "ok": True,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_sec": round(elapsed, 3),
        "error": None,
    }


def tool_explain(db_path: str | Path, sql: str) -> dict[str, Any]:
    """
    Возвращает план выполнения (EXPLAIN QUERY PLAN) и проверку синтаксиса.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"ok": False, "error": "База не найдена", "plan": "", "syntax_ok": False}

    from src.sql_validator import validate_select_only

    syntax_ok, syntax_err = validate_select_only(sql)
    if not syntax_ok:
        return {"ok": True, "plan": "", "syntax_ok": False, "syntax_error": syntax_err}

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.execute(f"EXPLAIN QUERY PLAN {sql.strip()}")
        plan_rows = cur.fetchall()
        conn.close()
        plan = "\n".join(str(r) for r in plan_rows)
    except Exception as e:
        err = _sanitize_db_error(e)
        plan = f"Ошибка SQL ({err['error_type']}): {err['message']}. {err['hint']}"

    return {"ok": True, "plan": plan, "syntax_ok": True}
