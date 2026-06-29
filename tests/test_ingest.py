"""Unit tests for ingestion parsing."""
from app.ingest import _to_float, normalize_subject, parse_result


def test_parse_result_passed():
    assert parse_result("ناجح بملاحظة حسن جدا") == (1, "ناجح", "حسن جدا")


def test_parse_result_passed_mid():
    assert parse_result("ناجح بملاحظة متوسّط") == (1, "ناجح", "متوسّط")


def test_parse_result_referred():
    assert parse_result("مؤجل إلى دورة المراقبة") == (0, "مؤجل", None)


def test_parse_result_rejected():
    assert parse_result("مرفوض") == (0, "مرفوض", None)


def test_normalize_subject_variants():
    assert normalize_subject("رياضيات") == "الرياضيات"
    assert normalize_subject("الانقليزية") == "الإنقليزية"
    assert normalize_subject("التاريخ و الجغرافيا") == "التاريخ والجغرافيا"
    assert normalize_subject("علوم فيزيائية") == "العلوم الفيزيائية"


def test_normalize_subject_unchanged():
    assert normalize_subject("الفلسفة") == "الفلسفة"
    assert normalize_subject("  الفلسفة  ") == "الفلسفة"   # whitespace trimmed


def test_to_float():
    assert _to_float("16.04") == 16.04
    assert _to_float("") is None
    assert _to_float(None) is None
    assert _to_float("nan") is None
