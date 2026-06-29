"""Integration tests for the API endpoints (FastAPI TestClient)."""
from app import llm


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["students"] > 0


def test_streams(client):
    r = client.get("/streams")
    assert r.status_code == 200
    assert len(r.json()) == 7


def test_students_filters(client):
    r = client.get("/students", params={
        "stream": "رياضيات", "min_bac": 15, "sort": "-total", "limit": 5,
    })
    assert r.status_code == 200
    d = r.json()
    assert all(i["stream"] == "رياضيات" for i in d["items"])
    assert all(i["total"] >= 15 for i in d["items"])
    # sorted descending by total
    totals = [i["total"] for i in d["items"]]
    assert totals == sorted(totals, reverse=True)


def test_students_bad_sort(client):
    r = client.get("/students", params={"sort": "drop_table"})
    assert r.status_code == 400


def test_filters_options(client):
    d = client.get("/filters").json()
    assert len(d["streams"]) == 7
    assert set(d["statuses"]) == {"ناجح", "مؤجل", "مرفوض"}
    # mentions are honor grades only (no مؤجل/مرفوض)
    assert "مؤجل" not in d["mentions"] and "مرفوض" not in d["mentions"]
    assert "bac_range" in d and "annual_range" in d


def test_filters_cascade(client):
    """Selecting رياضة narrows mentions to co-existing values."""
    d = client.get("/filters", params={"stream": "رياضة"}).json()
    assert "حسن جدا" not in d["mentions"]   # no رياضة student has it


def test_stats_pass_rates_shape(client):
    d = client.get("/stats/pass-rates").json()
    assert "data" in d and "chart" in d
    assert d["chart"]["chart"]["type"] == "bar"


def test_stats_status_totals(client):
    d = client.get("/stats/status").json()
    assert sum(r["count"] for r in d["data"]) > 0
    assert {r["status"] for r in d["data"]} == {"ناجح", "مؤجل", "مرفوض"}


def test_ask_status(client):
    r = client.get("/ask/status")
    assert r.status_code == 200
    assert "enabled" in r.json()


def test_ask_without_key_returns_503(client):
    if llm.is_configured():
        return  # skip when a key is present
    r = client.post("/ask", json={"question": "كم عدد الناجحين"})
    assert r.status_code == 503


def test_upload_rejects_bad_csv(client):
    r = client.post("/datasets", files={"file": ("bad.csv", "col1,col2\n1,2\n", "text/csv")})
    assert r.status_code == 422   # missing required columns
