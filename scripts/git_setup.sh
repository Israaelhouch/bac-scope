#!/usr/bin/env bash
# Run ONCE on your own machine (git cannot run on the sandbox mount).
# From the bac-scope/ directory:  bash scripts/git_setup.sh
#
# This reconstructs a phase-by-phase history from the current files: one feature
# branch + commit per phase, each merged into `develop`, then `develop` -> `main`.
# (Because the code was built where git couldn't run, intermediate commits are a
# reconstruction, not the original keystroke-by-keystroke history.)
set -e
cd "$(dirname "$0")/.."   # -> bac-scope/

rm -rf .git
git init -q
git config user.email "softylines.smartb@gmail.com"
git config user.name "Smartdev"
git checkout -q -b main

phase () {  # phase <branch> <message> <files...>
  local branch="$1"; local msg="$2"; shift 2
  git checkout -q develop
  git checkout -q -b "$branch"
  git add "$@"
  git commit -q -m "$msg"
  git checkout -q develop
  git merge -q --no-ff "$branch" -m "merge: $branch"
}

# ---- scaffold (on main) ----
git add .gitignore requirements.txt .env.example
git commit -q -m "chore: scaffold project (gitignore, requirements, env)"
git branch develop

# ---- phases ----
phase feat/phase-1-data-layer \
  "feat(data): SQLite schema, CSV ingestion, seed (7 streams, 713 students)" \
  app/__init__.py app/db.py app/ingest.py scripts/seed.py data/raw

phase feat/phase-2-core-rest \
  "feat(api): core REST (students, institutions, streams, filters) + app wiring + CORS" \
  app/models.py app/routers/__init__.py app/routers/students.py \
  app/routers/institutions.py app/routers/meta.py app/main.py

phase feat/phase-2-ui \
  "feat(ui): demo web UI with cascading (faceted) filters" \
  web/index.html

phase feat/phase-3-stats-charts \
  "feat(stats): stats endpoints + full ApexCharts specs (+ raw data)" \
  app/charts.py app/routers/stats.py

phase feat/phase-4-upload \
  "feat(datasets): CSV upload + auto-merge endpoint" \
  app/routers/datasets.py

# ---- docs + this script ----
git checkout -q develop
git add README.md scripts/git_setup.sh
git commit -q -m "docs: README, endpoint reference, git setup script"

# ---- release to main ----
git checkout -q main
git merge -q --no-ff develop -m "release: phases 1-4 (data, REST, UI, stats/charts, upload)"

echo "Done. History:"
git log --oneline --graph --all
echo
echo "Branches:"
git branch
