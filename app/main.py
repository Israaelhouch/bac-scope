"""bac-scope API — FastAPI application entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import datasets, institutions, meta, stats, students

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


@app.options("/{rest_of_path:path}", include_in_schema=False)
def preflight(rest_of_path: str):
    """Answer any OPTIONS request (e.g. CORS preflight) with 204 instead of 405."""
    return Response(status_code=204)


@app.get("/info", tags=["meta"])
def info():
    return {"name": "bac-scope", "version": "0.2.0", "docs": "/docs", "ui": "/"}


@app.get("/health", tags=["meta"])
def health():
    from .db import get_connection

    conn = get_connection(read_only=True)
    n = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    conn.close()
    return {"status": "ok", "students": n}


# Serve the web UI at "/" (mounted last so API routes take precedence).
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="ui")
