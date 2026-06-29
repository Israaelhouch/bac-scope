# bac-scope — Solution Overview

A backend service that ingests Tunisian Baccalaureate results and exposes them
for analysis. Built **API-first** so a frontend can be developed independently
on top of it.

**Stack:** FastAPI + SQLite (Python). Auto-generated OpenAPI docs at `/docs`,
CORS enabled. A demo web UI ships at `/` for testing — it does not constrain the
real frontend.

---

## 1. Data model

Two tables:

- **`students`** — one row per student: `registration_number` (PK), `name`,
  `institution`, `stream`, `status` (3-way outcome: ناجح / مؤجل / مرفوض),
  `passed` (1 only if ناجح — used for pass-rate math), `mention` (honor grade,
  passed students only), `total` (معدل الباكالوريا — the final bac average),
  `moyenne` (المعدل السنوي — annual average).
- **`grades`** — long format: one row per (student, subject, score).

**Why long-format grades:** streams have different subjects and new streams/years
appear over time. Long format absorbs any subject set with **no schema change**.
Trade-off: subject queries join `grades`↔`students`.

---

## 2. Ingestion

Auto-detects **two CSV formats** from the header:

1. **Arabic format** — Arabic headers, one column per named subject.
2. **Export format** — English headers (`registration_number`, `student_name`,
   `section`, `result_status`, …) followed by a *variable* number of
   `grade_N`/`subject_N` pairs (parsed flexibly, so students with extra subjects
   aren't dropped).

All text is normalized (tatweel + diacritics stripped, e.g. `الـرِّيـاضـيـات` →
`الرياضيات`) and subject/stream name variants canonicalized, so both formats
merge into one consistent store.

Two entry points, **opposite behaviors**:

- **`python -m scripts.seed`** (CLI, admin) — **full rebuild**: drops everything
  and reloads from `data/raw/` (or the committed sample). For setup / schema changes.
- **`POST /datasets`** (API, end users) — **incremental merge**, keyed by
  registration number (`INSERT OR REPLACE`): new students added, existing ones
  updated, others untouched. Idempotent. Intentionally *not* destructive.

---

## 3. API design

Every request: **HTTP → FastAPI route → parameterized SQL → JSON.** The DB is
never exposed directly; each endpoint is a fixed, safe question. Three kinds:

- **Record endpoints** (`/students`, `/students/{id}`) — return rows; filtered via
  query params turned into **parameterized** SQL (injection-safe).
- **Aggregate/stats endpoints** (`/stats/*`) — computed numbers (`GROUP BY`) plus
  a ready-to-render chart spec.
- **Meta endpoint** (`/filters`) — dropdown options, **faceted/cascading**: pass
  the current selection and each list narrows to values that still co-exist, so
  the user can never build an empty-result filter.

**Decisions:**

- **REST + query params** (over a generic `/query` or GraphQL): self-documenting
  (the `/docs` page is the frontend's spec), predictable, one endpoint per
  analysis view. The flexibility cost is covered by the `/ask` layer.
- **Backend returns chart specs (ApexCharts) + raw data:** the frontend renders a
  chart in one line, or ignores the spec and uses `data`. Same response shape for
  stats and `/ask`, so the frontend has one rendering path.
- **Two distinct averages, never conflated:** `total` = معدل الباك (decides
  pass/mention), `moyenne` = المعدل السنوي. Both are filterable, sortable, and
  aggregated (`avg_bac` / `avg_annual`).

---

## 4. AI layer (`/ask`) — natural language → SQL

Pipeline:

```
question → build prompt (schema linking) → LLM writes SQL
        → validate → run read-only → auto-pick chart → { sql, data, chart }
```

**Schema linking** is the core idea: we don't rely on the model "knowing" the DB;
every request injects the exact schema, a **glossary** (user vocabulary → column,
e.g. `mou3adel/معدل → total`, `najah → status='ناجح'`), the **live distinct
values** of categorical columns (exact stream/mention/status strings), and a few
**worked examples** (including hard cases: correlated subqueries, subject-vs-stream).
Principle: *capability sets the ceiling; context engineering raises the floor.*

**Safety — defense in depth:**
1. The model only *proposes* SQL; it never touches the DB.
2. A validator allows a **single `SELECT`** only (no DELETE/UPDATE/multi-statement)
   and enforces a `LIMIT`.
3. Execution runs on a **read-only** SQLite connection — a write can't reach the
   DB even if it slipped past the validator.

The generated SQL is returned in the response for **transparency/debuggability**.

**Auto-visualization** is deterministic (not the LLM): it picks a chart from the
result *shape* — single value → KPI, category+count → pie, category+measure →
bar, two numerics → scatter, else table. This keeps the LLM confined to one job.

**LLM provider:** Groq (free tier), behind a pluggable adapter (swappable via
env). `/ask` returns 503 if no key is configured; the rest of the API runs
normally without it.

---

## 5. Quality & operations

- **Tests:** 37 unit + integration tests (pytest) on an isolated temp DB —
  parsing, normalization, SQL validation, the auto-viz chooser, and the endpoints
  (filters, cascading, stats shape, upload validation).
- **Eval harness:** **execution-accuracy** for `/ask` — each case is a question +
  a known-correct *gold* SQL; the runner generates SQL, runs both, and compares
  **results** (not SQL text). Currently 9/9; doubles as a regression suite. This
  approach caught a real bug: a correlated subquery that looked correct but
  computed the global average instead of per-stream.
- **Schema-check:** startup banner + `/health` warn to re-seed if the DB is
  missing or stale (instead of a cryptic 500).
- **Privacy:** real student data is gitignored and was purged from git history;
  an anonymized synthetic sample is committed so the repo runs out of the box.
- **`Makefile`** for common tasks (`install`, `seed`, `run`, `test`, `eval`).

---

## 6. Key decisions (summary)

| Decision | Why | Trade-off |
|---|---|---|
| API-first | Frontend-agnostic; reusable | Demo UI is just for testing |
| Long-format grades | New streams/subjects need no schema change | Extra join |
| REST + query params | Self-documenting, predictable | Long-tail covered by `/ask` |
| Backend owns chart specs | Frontend renders in one line | Library coupling (mitigated: raw data also returned) |
| LLM confined to SQL + read-only | NL flexibility without write access / blind trust | — |
| Execution-based eval | Many SQLs are correct; results are what matter | Needs gold queries |
| Purge + synthetic sample | Privacy + still runnable | History rewrite (one-time) |

**Throughline:** predictable, safe, and measurable — fixed endpoints for known
questions, a guard-railed AI layer for the long tail, and tests + an eval harness
so quality is measured, not assumed.
