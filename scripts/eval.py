"""Evaluation runner for /ask text-to-SQL (execution accuracy).

Usage (from the bac-scope/ folder, with the DB seeded):
    python -m scripts.eval            # real run — needs GROQ_API_KEY in .env
    python -m scripts.eval --mock     # offline: uses gold SQL as the "model"
                                      # output, to verify the harness itself

For each case it generates SQL from the question, runs it AND the gold SQL
read-only, and compares the results. Prints PASS/FAIL per case + overall
accuracy. On failure it shows both SQLs so you can turn the gap into a new
prompt rule/example.
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


def compare(mode: str, gold: list[dict], model: list[dict]) -> bool:
    if mode == "scalar":
        g, m = _scalar(gold), _scalar(model)
        try:
            return abs(float(g) - float(m)) < 0.05
        except (TypeError, ValueError):
            return str(g) == str(m)
    g, m = _norm(gold), _norm(model)
    if mode == "ordered":
        return g == m
    return set(g) == set(m)  # "set"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true",
                    help="use each case's gold SQL as the model output (tests the harness)")
    args = ap.parse_args()

    conn = get_connection(read_only=True)
    passed = 0
    for i, case in enumerate(CASES, 1):
        q, gold_sql, mode = case["q"], case["gold"], case.get("mode", "set")
        try:
            if args.mock:
                model_sql = gold_sql
            else:
                prompt = nl2sql.build_system_prompt(conn, scope=case.get("scope"))
                model_sql = nl2sql.validate_sql(llm.generate_sql(q, prompt))
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
    print(f"\nAccuracy: {passed}/{total} = {100 * passed / total:.0f}%")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
