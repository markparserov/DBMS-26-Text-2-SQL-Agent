"""Тесты инструментов: schema, query, explain (требуют SQLite или пропуск)."""
import tempfile
import sqlite3
import pytest
from pathlib import Path

from src.tools import tool_schema, tool_query, tool_explain


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE test_t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO test_t VALUES (1, 'a')")
    conn.commit()
    conn.close()
    yield path
    Path(path).unlink(missing_ok=True)


def test_tool_schema(temp_db):
    out = tool_schema(temp_db)
    assert out["ok"] is True
    assert "test_t" in out["schema"]
    assert "CREATE TABLE" in out["schema"]


def test_tool_query_select(temp_db):
    out = tool_query(temp_db, "SELECT * FROM test_t", max_rows=10, validate=True)
    assert out["ok"] is True
    assert out["row_count"] == 1
    assert out["rows"][0]["id"] == 1 and out["rows"][0]["name"] == "a"


def test_tool_query_rejects_insert(temp_db):
    out = tool_query(temp_db, "INSERT INTO test_t VALUES (2, 'b')", validate=True)
    assert out["ok"] is False
    assert "error" in out


def test_tool_explain(temp_db):
    out = tool_explain(temp_db, "SELECT * FROM test_t")
    assert out["ok"] is True
    assert out["syntax_ok"] is True
    assert "plan" in out
