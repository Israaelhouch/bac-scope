"""Evaluation runner for /ask text-to-SQL (execution accuracy).

Usage (from the bac-scope/ folder, with the DB seeded):
    python -m scripts.eval            # real run — needs GROQ_API_KEY in .env
    python -m scripts.eval --mock     # offline: uses gold SQL as the "model"
                                      # output, to verify the harness itself
    python -m scripts.eval --model openai/gpt-oss-120b    # score one model
    python -m scripts.eval --list-models                  # what the key can use

For each case it generates SQL from the question, runs it AND the gold SQL
read-only, and compares the results. Prints PASS/FAIL per case + overall
accuracy. On failure it shows both SQLs so you can turn the gap into a new
prompt rule/example.

Because scoring is per-model, this doubles as a model chooser: run it against
each candidate and let execution accuracy decide the default, rather than
picking whichever ID a tutorial happened to use.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import llm, nl2sql  # noqa: E402
from app.db import get_connection  # noqa: E402
from evals.cases import CASES  # noqa: E402


def _norm(rows: list[dict]) -> list[tuple]:
    """Normalize rows to comparable tuples (round floats, stringify).

    Values within a row are sorted so the comparison is insensitive to the
    column ORDER the model happened to SELECT (e.g. name,total vs total,name).
    """
    out = []
    for r in rows:
        vals = []
        for v in r.values():
            if isinstance(v, float):
                v = round(v, 2)
            vals.append(str(v))
        out.append(tuple(sorted(vals)))
    return out


def _scalar(rows: list[dict]):
    if not rows:
        return None
    return list(rows[0].values())[0]


def _covers(gold_row: tuple, model_row: tuple) -> bool:
    """True if a model row carries every value the gold row has.

    A model that answers "who passed" with (name, stream, total) is not wrong
    because gold only asked for (name, total) — it returned a superset. Strict
    equality would score that as a miss, so extra columns are tolerated as long
    as nothing gold asked for is missing.
    """
    remaining = list(model_row)
    for value in gold_row:
        if value in remaining:
            remaining.remove(value)
        else:
            return False
    return True


def _matches_with_extra_columns(gold: list[tuple], model: list[tuple]) -> bool:
    """Pair every gold row with a distinct model row that covers it."""
    if len(gold) != len(model):
        return False
    unused = list(model)
    for gold_row in gold:
        match = next((m for m in unused if _covers(gold_row, m)), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def compare(mode: str, gold: list[dict], model: list[dict]) -> bool:
    if mode == "scalar":
        g, m = _scalar(gold), _scalar(model)
        try:
            return abs(float(g) - float(m)) < 0.05
        except (TypeError, ValueError):
            return str(g) == str(m)
    g, m = _norm(gold), _norm(model)
    if mode == "ordered":
        return g == m or (len(g) == len(m) and all(map(_covers, g, m)))
    return set(g) == set(m) or _matches_with_extra_columns(g, m)  # "set"


def _print_available_models() -> int:
    """Print the chat models this API key can use. Returns an exit code."""
    if not llm.is_configured():
        print("GROQ_API_KEY is not set — add it to .env first.")
        return 1
    import os

    from groq import Groq

    models = llm.available_models(Groq(api_key=os.environ["GROQ_API_KEY"]))
    if not models:
        print("Could not list models (check the key and your connection).")
        return 1
    print("Chat models available to this key:")
    for m in models:
        marker = "  <- default" if m == llm.DEFAULT_MODEL else ""
        print(f"  {m}{marker}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true",
                    help="use each case's gold SQL as the model output (tests the harness)")
    ap.add_argument("--model", default=None,
                    help="Groq model ID to score (default: GROQ_MODEL, else the built-in default)")
    ap.add_argument("--list-models", action="store_true",
                    help="list the chat models this API key can use, then exit")
    args = ap.parse_args()

    if args.list_models:
        sys.exit(_print_available_models())

    model = args.model or llm.configured_model()
    if not args.mock:
        print(f"Model: {model}\n")

    conn = get_connection(read_only=True)
    passed = 0
    for i, case in enumerate(CASES, 1):
        q, gold_sql, mode = case["q"], case["gold"], case.get("mode", "set")
        try:
            if args.mock:
                model_sql = gold_sql
            else:
                prompt = nl2sql.build_system_prompt(conn, scope=case.get("scope"))
                model_sql = nl2sql.validate_sql(llm.generate_sql(q, prompt, model=model))
            _, model_rows = nl2sql.run_query(model_sql, conn)
            _, gold_rows = nl2sql.run_query(gold_sql, conn)
            ok = compare(mode, gold_rows, model_rows)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i:>2}] ERROR  {q[:50]}\n       {exc}")
            continue

        passed += ok
        print(f"[{i:>2}] {'PASS' if ok else 'FAIL'}  {q[:50]}")
        if not ok:
            print(f"       model: {model_sql}")
            print(f"       gold : {gold_sql}")
    conn.close()

    total = len(CASES)
    label = "gold SQL (mock)" if args.mock else model
    print(f"\nAccuracy [{label}]: {passed}/{total} = {100 * passed / total:.0f}%")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
