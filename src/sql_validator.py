"""
Валидация и санитизация SQL: только SELECT, лимит строк.
"""
import re
from typing import Any

try:
    import sqlparse
except ImportError:
    sqlparse = None


# Запрещённые ключевые слова (нижний регистр)
FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "create", "alter", "truncate",
    "exec", "execute", "grant", "revoke", "commit", "rollback", "attach",
    "detach", "vacuum", "reindex", "pragma",  # pragma — опционально разрешать, для baseline запрещаем
}


def validate_select_only(sql: str) -> tuple[bool, str]:
    """
    Проверяет, что в запросе только SELECT (read-only).
    Возвращает (ok, error_message).
    """
    if not sql or not sql.strip():
        return False, "Пустой запрос"

    if sqlparse is None:
        # Fallback: простая проверка по первому слову и запрещённым подстрокам
        normalized = re.sub(r"\s+", " ", sql.strip()).lower()
        first_word = normalized.split()[0] if normalized.split() else ""
        if first_word != "select":
            return False, "Разрешён только SELECT"
        for kw in FORBIDDEN_KEYWORDS:
            if kw != "select" and re.search(r"\b" + re.escape(kw) + r"\b", normalized):
                return False, f"Запрещённое ключевое слово: {kw}"
        return True, ""

    try:
        parsed = sqlparse.parse(sql)
    except Exception as e:
        return False, f"Ошибка разбора SQL: {e}"

    if not parsed:
        return False, "Не удалось разобрать SQL"

    normalized = re.sub(r"\s+", " ", sql).lower()
    if not normalized.strip().startswith("select"):
        return False, "Запрос должен начинаться с SELECT"
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", normalized):
            return False, f"Запрещённое ключевое слово: {kw}"
    return True, ""


def enforce_limit(sql: str, max_rows: int = 100) -> str:
    """
    Добавляет LIMIT к запросу, если его ещё нет, или уменьшает существующий до max_rows.
    """
    if max_rows <= 0:
        return sql
    sql = sql.strip().rstrip(";")
    # Простая эвристика: ищем LIMIT \d+ в конце и заменяем/добавляем
    limit_match = re.search(r"\s+LIMIT\s+(\d+)\s*$", sql, re.IGNORECASE)
    if limit_match:
        existing = int(limit_match.group(1))
        new_limit = min(existing, max_rows)
        sql = sql[: limit_match.start()] + f" LIMIT {new_limit}"
    else:
        sql = sql + f" LIMIT {max_rows}"
    return sql


def validate_and_prepare(sql: str, max_rows: int = 100) -> tuple[bool, str, str]:
    """
    Валидация (только SELECT) и добавление LIMIT.
    Возвращает (ok, error_message, prepared_sql).
    """
    ok, err = validate_select_only(sql)
    if not ok:
        return False, err, sql
    prepared = enforce_limit(sql, max_rows)
    return True, "", prepared
