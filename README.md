# bac-scope

A backend API to query and analyze Tunisian Baccalaureate results. Built with
FastAPI + SQLite. See `../ROADMAP.md` for the full plan and phases.

Status: **Phase 1 (data layer)** and **Phase 2 (core REST endpoints)** complete.

---

## Run it locally

From inside the `bac-scope/` folder:

```bash
# 1. (once) create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. (once) build the database from the 7 CSVs in data/raw/
python -m scripts.seed

# 3. start the API
uvicorn app.main:app --reload
```

Then open:

- **http://127.0.0.1:8000/** — the **web UI**: pick filters from dropdowns
  (stream, mention, institution, average range, sort), see results in a table,
  click any student to view all their grades.
- **http://127.0.0.1:8000/docs** — the interactive API docs (raw JSON, "Try it out").

> If the table is empty, the database hasn't been seeded — run
> `python -m scripts.seed` (step 2) and restart the server.

---

## Endpoints (Phase 2)

| Endpoint | What it returns |
|---|---|
| `GET /health` | Status + student count |
| `GET /filters` | **Selectable filter values**, cascading: pass current selection (e.g. `?stream=رياضة`) and each list narrows to values that still co-exist (faceted) |
| `GET /streams` | Each stream with count, pass rate, average |
| `GET /institutions` | Each school with count, pass rate, average |
| `GET /students` | Filtered, sorted, paginated list of students |
| `GET /students/{registration_number}` | One student + all their grades |
| `GET /stats/pass-rates` | Pass rate per `stream` or `institution` |
| `GET /stats/status` | Outcome breakdown — ناجح / مؤجل / مرفوض (optional `stream`) |
| `GET /stats/mentions` | Honor-grade distribution, passed students (optional `stream`) |
| `GET /stats/subject-averages` | Average grade per subject (optional `stream`) |
| `GET /stats/top-performers` | Top achievers; `per_stream`, `subject`, `by`, `limit` |
| `GET /stats/remontada` | Biggest gap of final total over annual average |
| `GET /datasets` | List of loaded CSV files (stream, rows, uploaded_at) |
| `POST /datasets` | Upload a CSV — auto-normalized and merged into the database |
| `GET /ask/status` | Whether the natural-language endpoint is enabled |
| `POST /ask` | **Natural-language question → SQL → result + auto-chart** |

### `/ask` — natural language (AI)

Send a question; the LLM writes SQL, the server validates it (SELECT-only,
single statement, enforced LIMIT) and runs it **read-only**, then auto-picks a
chart by result shape.

Optionally scope the question to a subset (soft-enforced via the prompt):

```
POST /ask
{ "question": "أفضل 5",
  "scope": { "stream": "رياضيات", "passed": true, "min_avg": 15 } }
```

```
POST /ask   { "question": "أفضل 5 معدلات في الرياضيات" }

{
  "sql": "SELECT name, moyenne FROM students WHERE stream='رياضيات' ORDER BY moyenne DESC LIMIT 5",
  "columns": ["name", "moyenne"],
  "row_count": 5,
  "data": [ ... ],
  "kind": "bar",            // stat | bar | table | empty
  "chart": { ...ApexCharts spec... }
}
```

**Enable it:** get a free key at https://console.groq.com, then in `.env`:

```
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

Without a key, `/ask` returns `503` and the rest of the API works normally.
Safety: the LLM only proposes SQL; writes are blocked by validation **and** by a
read-only database connection.

**Every `/stats/*` response has the same shape:** raw `data` plus a full
**ApexCharts** spec.

```json
{
  "data":  [ { "group_name": "رياضيات", "pass_rate": 81.5, ... }, ... ],
  "chart": {                                  // a full ApexCharts options object
    "chart":  { "type": "bar", "height": 330 },
    "series": [ { "name": "نسبة النجاح %", "data": [81.5, ...] } ],
    "xaxis":  { "categories": ["رياضيات", ...] },
    "title":  { "text": "نسبة النجاح حسب الشعبة" }
  }
}
```

- Render the chart directly:
  `const c = new ApexCharts(el, resp.chart); c.render();`
- Or ignore `chart` and build your own visual / table from `data`.

> The backend produces the chart spec; the frontend only renders it. Frontend
> uses **ApexCharts** (`npm i apexcharts` or `react-apexcharts`).

### `/students` filters (combine any)

| Param | Meaning | Example |
|---|---|---|
| `stream` | Stream (شعبة) | `stream=رياضيات` |
| `institution` | Exact school name | `institution=معهد بوعرقوب` |
| `status` | Outcome: ناجح / مؤجل / مرفوض | `status=مؤجل` |
| `mention` | Honor grade (passed only) | `mention=حسن جدا` |
| `passed` | Passed (ناجح) only — for pass-rate | `passed=true` |
| `min_bac` / `max_bac` | **Bac average** range — معدل الباك (`total`) | `min_bac=15` |
| `min_annual` / `max_annual` | **Annual average** range — المعدل السنوي (`moyenne`) | `min_annual=12` |
| `search` | Name contains | `search=محمد` |
| `sort` | Sort field, `-` = desc (`total`, `moyenne`, `name`, …) | `sort=-total` |

> **Two averages, kept distinct:** `total` = معدل الباكالوريا (the final bac
> average, determines pass/mention) and `moyenne` = المعدل السنوي (annual average).
> Plain "معدل" means `total`. Both are filterable, sortable, and aggregated
> (`avg_bac` / `avg_annual` on `/institutions` and `/streams`).
| `limit` / `offset` | Pagination | `limit=20&offset=40` |

### `/institutions` params

`stream` (restrict to one stream), `min_count` (min students per school),
`sort` (`-pass_rate`, `count`, `avg_moyenne`, `institution`).

### Example requests

```
# Top 5 students in math with average >= 15
GET /students?stream=رياضيات&min_avg=15&sort=-moyenne&limit=5

# Best-performing schools with at least 10 students
GET /institutions?sort=-pass_rate&min_count=10

# Search a student by name
GET /students?search=محمد

# Upload a new stream/year CSV (multipart form: file + optional stream)
curl -F "file=@results_2026.csv" -F "stream=رياضيات" http://127.0.0.1:8000/datasets
```

Two CSV formats are auto-detected:

1. **Arabic format** — Arabic headers (`رقم التسجيل`, `الاسم`, `النتيجة`, …),
   one column per named subject (the original files).
2. **Export format** — English headers (`registration_number`, `student_name`,
   `section`, `result_status`, `overall_grade`, `annual_average`) followed by a
   variable number of `grade_N` / `subject_N` pairs.

Both are normalized the same way (tatweel + diacritics stripped, subject/stream
names canonicalized). Rows without a name, or files matching neither format, are
rejected. Re-uploading a student (same registration number) updates the record.

---

## Tests

```bash
pytest            # unit + API integration tests (runs on an isolated temp DB)
```

Covers ingestion parsing, subject normalization, SQL validation (SELECT-only,
limit injection, write rejection), the auto-viz chooser, and the API endpoints
(filters, cascading, stats shape, status, upload validation).

## Evaluating /ask (text-to-SQL accuracy)

A regression suite measures `/ask` by **execution accuracy**: each case has a
question + a known-correct "gold" SQL; the runner generates SQL from the
question, runs both read-only, and compares the *results*.

```bash
python -m scripts.eval          # real run — needs GROQ_API_KEY in .env
python -m scripts.eval --mock   # offline: verifies the harness + gold SQLs
```

Cases live in `evals/cases.py` and double as regression tests — each guards a
fix we made to the prompt (e.g. معدل→total not AVG, no spurious status filter,
correlated-subquery aliasing). When a real question comes back wrong, add it as a
new case, fix the prompt, and re-run until accuracy is back to 100%.

## Notes

- The database (`data/bac.db`) is generated by the seed script and is gitignored.
- Override the DB location with the `BACSCOPE_DB` environment variable.
- All read endpoints use a read-only SQLite connection.
