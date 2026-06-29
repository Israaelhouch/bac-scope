"""bac-scope API — FastAPI application entry point."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env (GROQ_API_KEY, etc.) before anything reads the environment.
load_dotenv()

from .routers import ask, datasets, institutions, meta, stats, students  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="bac-scope API",
    description="Query and analyze Tunisian Baccalaureate results.",
    version="0.2.0",
)

# Allow the frontend (any origin during development) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(students.router)
app.include_router(institutions.router)
app.include_router(stats.router)
app.include_router(datasets.router)
app.include_router(ask.router)


@app.on_event("startup")
def _check_schema_on_startup():
    """Warn loudly (instead of cryptic 500s) if the DB is missing or stale."""
    from .db import schema_status

    s = schema_status()
    if s["state"] == "missing":
        print("\n" + "=" * 60)
        print("⚠️  No database found (data/bac.db).")
        print("    Run:  python -m scripts.seed")
        print("=" * 60 + "\n")
    elif s["state"] == "stale":
        print("\n" + "=" * 60)
        print("⚠️  Database schema is OUT OF DATE.")
        print("    Missing columns: " + ", ".join(s["missing_columns"]))
        print("    Run:  python -m scripts.seed   to rebuild it.")
        print("=" * 60 + "\n")


@app.options("/{rest_of_path:path}", include_in_schema=False)
def preflight(rest_of_path: str):
    """Answer any OPTIONS request (e.g. CORS preflight) with 204 instead of 405."""
    return Response(status_code=204)


@app.get("/info", tags=["meta"])
def info():
    return {"name": "bac-scope", "version": "0.2.0", "docs": "/docs", "ui": "/"}


@app.get("/health", tags=["meta"])
def health():
    from .db import schema_status, get_connection

    s = schema_status()
    if s["state"] != "ok":
        return {"status": s["state"], "hint": "run: python -m scripts.seed",
                "missing_columns": s["missing_columns"]}
    conn = get_connection(read_only=True)
    n = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    conn.close()
    return {"status": "ok", "students": n}


# Serve the web UI at "/" (mounted last so API routes take precedence).
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="ui")
