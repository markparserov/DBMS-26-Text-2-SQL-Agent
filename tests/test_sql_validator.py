"""Тесты валидатора SQL: только SELECT, запрещённые ключевые слова, LIMIT."""
import pytest
from src.sql_validator import validate_select_only, enforce_limit, validate_and_prepare


def test_empty_rejected():
    ok, err = validate_select_only("")
    assert ok is False
    assert "Пустой" in err or "SELECT" in err


def test_select_only_allowed():
    ok, err = validate_select_only("SELECT 1")
    assert ok is True
    ok, err = validate_select_only("  SELECT * FROM t LIMIT 10  ")
    assert ok is True


def test_insert_rejected():
    ok, err = validate_select_only("INSERT INTO t VALUES (1)")
    assert ok is False
    assert "select" in err.lower() or "запрещён" in err.lower() or "insert" in err.lower()


def test_update_delete_drop_rejected():
    for sql in ["UPDATE t SET x=1", "DELETE FROM t", "DROP TABLE t"]:
        ok, err = validate_select_only(sql)
        assert ok is False, sql


def test_enforce_limit_adds_limit():
    sql = "SELECT * FROM t"
    out = enforce_limit(sql, 50)
    assert "LIMIT 50" in out.upper()


def test_enforce_limit_reduces_existing():
    sql = "SELECT * FROM t LIMIT 999"
    out = enforce_limit(sql, 10)
    assert "LIMIT 10" in out.upper()


def test_validate_and_prepare_ok():
    ok, err, prepared = validate_and_prepare("SELECT 1", max_rows=5)
    assert ok is True
    assert "LIMIT 5" in prepared


def test_validate_and_prepare_rejects_non_select():
    ok, err, prepared = validate_and_prepare("DELETE FROM t", max_rows=5)
    assert ok is False
    assert prepared == "DELETE FROM t"
