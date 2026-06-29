#!/usr/bin/env bash
# Commit the post-phase-4 work (NL→SQL, status model, averages, eval, charts).
# Run ONCE on your Mac, from the bac-scope/ folder, AFTER scripts/git_setup.sh:
#     bash scripts/commit_phase5.sh
# This does NOT rewrite history — it adds new commits on a feature branch.
set -e
cd "$(dirname "$0")/.."   # -> bac-scope/

git rev-parse --git-dir >/dev/null 2>&1 || { echo "No git repo. Run scripts/git_setup.sh first."; exit 1; }

git checkout develop
git checkout -b feat/phase-5-ask-nl-sql

commit () { git add "$@" && git commit -m "$MSG"; }

MSG="feat(model): 3-way status (ناجح/مؤجل/مرفوض), subject normalization, mention=honor-only"
commit app/db.py app/ingest.py app/models.py

MSG="feat(api): bac vs annual averages, status filters, faceted /filters"
commit app/routers/students.py app/routers/institutions.py app/routers/meta.py

MSG="feat(ask): NL→SQL via Groq, schema-linking prompt, read-only safety validation"
commit app/llm.py app/nl2sql.py app/routers/ask.py app/main.py

MSG="feat(charts): smarter auto-viz (pie/bar/grouped/scatter) + /stats/status"
commit app/autoviz.py app/charts.py app/routers/stats.py

MSG="feat(ui): ask tab, 3-way status dropdown + pill, charts tab, bac/annual filters"
commit web/index.html

MSG="test: pytest suite (unit + API) + execution-accuracy eval harness"
commit evals scripts/eval.py tests

MSG="docs+chore: README, deps (groq/python-dotenv), .env example, commit script"
commit README.md requirements.txt .env.example scripts/commit_phase5.sh

# catch anything not explicitly listed (skips if nothing remains)
git add -A && git commit -m "chore: remaining phase-5 changes" || true

git checkout develop
git merge --no-ff feat/phase-5-ask-nl-sql -m "merge: phase 5 (NL→SQL, status, averages, eval, charts)"
git checkout main
git merge --no-ff develop -m "release: phase 5"

echo "Done. History:"
git log --oneline --graph -15
