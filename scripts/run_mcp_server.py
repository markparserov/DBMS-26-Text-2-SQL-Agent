#!/usr/bin/env python3
"""
MCP-сервер с инструментами schema, query, explain для Text-2-SQL.
Запуск: python scripts/run_mcp_server.py
Конфиг: config.yaml / config.example.yaml и env.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.tools import tool_schema, tool_query, tool_explain

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

mcp = FastMCP("SQL Agent")

cfg = load_config()
DB = str(cfg["db_path"])
DESC = str(cfg["schema_descriptions_path"])
MAX_ROWS = cfg.get("max_rows", 100)
TIMEOUT = cfg.get("query_timeout_sec", 30)


if FastMCP is not None:

    @mcp.tool()
    def schema(format: str = "full") -> str:
        """Схема БД: DDL и комментарии. format: full или compact."""
        out = tool_schema(DB, DESC, format=format)
        return out.get("schema", out.get("error", "")) if out.get("ok") else out.get("error", "")

    @mcp.tool()
    def query(sql: str, limit: int | None = None, timeout_sec: float | None = None) -> str:
        """Выполняет SELECT. limit — макс. строк, timeout_sec — таймаут."""
        limit = limit if limit is not None else MAX_ROWS
        timeout_sec = timeout_sec if timeout_sec is not None else float(TIMEOUT)
        out = tool_query(DB, sql, max_rows=limit, timeout_sec=timeout_sec, validate=True)
        if not out.get("ok"):
            return out.get("error", "Ошибка")
        rows = out.get("rows", [])
        if not rows:
            return "Строк: 0."
        keys = list(rows[0].keys())
        return "\n".join(["\t".join(keys)] + ["\t".join(str(r.get(k, "")) for k in keys) for r in rows])

    @mcp.tool()
    def explain(sql: str) -> str:
        """EXPLAIN QUERY PLAN и проверка синтаксиса для SELECT."""
        out = tool_explain(DB, sql)
        if not out.get("ok"):
            return out.get("error", "")
        if not out.get("syntax_ok"):
            return out.get("syntax_error", "Синтаксическая ошибка")
        return out.get("plan", "")


def main() -> None:
    if FastMCP is None:
        print("Установите: pip install mcp", file=sys.stderr)
        sys.exit(1)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
