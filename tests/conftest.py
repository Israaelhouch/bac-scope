"""Shared pytest fixtures: a temp seeded DB and a TestClient.

We set BACSCOPE_DB to a temp file BEFORE importing the app, so the whole suite
runs against an isolated database seeded from data/raw — never the real one.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated test DB + ensure /ask is treated as disabled unless a key is set.
os.environ["BACSCOPE_DB"] = str(Path(tempfile.gettempdir()) / "bacscope_test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from scripts import seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seed_db():
    """Build the test database once for the whole session."""
    seed.main()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
