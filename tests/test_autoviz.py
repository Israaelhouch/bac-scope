"""Unit tests for the auto-visualization chooser."""
from app import autoviz


def test_empty():
    assert autoviz.build(["a"], [])["kind"] == "empty"


def test_stat_single_scalar():
    v = autoviz.build(["n"], [{"n": 415}])
    assert v["kind"] == "stat" and v["value"] == 415


def test_pie_small_int_distribution():
    rows = [{"s": "ناجح", "n": 415}, {"s": "مؤجل", "n": 185}, {"s": "مرفوض", "n": 113}]
    assert autoviz.build(["s", "n"], rows)["kind"] == "pie"


def test_bar_floats_are_measure_not_pie():
    rows = [{"s": f"st{i}", "a": 10.5 + i} for i in range(7)]
    assert autoviz.build(["s", "a"], rows)["kind"] == "bar"


def test_bar_horizontal_for_long_labels():
    rows = [{"name": "اسم طويل جدا لتلميذ رقم %d" % i, "v": i} for i in range(5)]
    v = autoviz.build(["name", "v"], rows)
    assert v["kind"] == "bar"
    assert v["chart"]["plotOptions"]["bar"]["horizontal"] is True


def test_grouped_two_measures():
    rows = [{"s": "x", "a": 1, "b": 2}, {"s": "y", "a": 3, "b": 4}]
    assert autoviz.build(["s", "a", "b"], rows)["kind"] == "grouped"


def test_scatter_two_numeric():
    rows = [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}]
    assert autoviz.build(["x", "y"], rows)["kind"] == "scatter"


def test_table_fallback():
    rows = [{"a": "x", "b": "y", "c": "z", "d": "w"}]
    assert autoviz.build(["a", "b", "c", "d"], rows)["kind"] == "table"
