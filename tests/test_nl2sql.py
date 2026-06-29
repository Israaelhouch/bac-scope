"""Unit tests for SQL validation and scope rendering."""
import pytest

from app import nl2sql


def test_validate_select_ok():
    assert nl2sql.validate_sql("SELECT 1").lower().startswith("select")


def test_validate_adds_limit():
    assert nl2sql.validate_sql("SELECT * FROM students").lower().endswith("limit 200")


def test_validate_keeps_existing_limit():
    sql = nl2sql.validate_sql("SELECT * FROM students LIMIT 5").lower()
    assert "limit 200" not in sql
    assert "limit 5" in sql


def test_validate_rejects_delete():
    with pytest.raises(ValueError):
        nl2sql.validate_sql("DELETE FROM students")


def test_validate_rejects_update():
    with pytest.raises(ValueError):
        nl2sql.validate_sql("UPDATE students SET passed = 1")


def test_validate_rejects_multi_statement():
    with pytest.raises(ValueError):
        nl2sql.validate_sql("SELECT 1; DROP TABLE students")


def test_validate_rejects_hidden_write():
    with pytest.raises(ValueError):
        nl2sql.validate_sql("SELECT * FROM students; DELETE FROM grades")


def test_scope_to_conditions():
    c = nl2sql.scope_to_conditions({"stream": "رياضيات", "min_bac": 15, "passed": True})
    assert "stream = 'رياضيات'" in c
    assert "total >= 15" in c
    assert "passed = 1" in c


def test_scope_empty():
    assert nl2sql.scope_to_conditions({}) == ""
