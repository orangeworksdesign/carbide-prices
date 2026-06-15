#!/usr/bin/env bash
# Daily wrapper for cron: scrape, then commit + push if the data changed.
set -euo pipefail
cd "$(dirname "$0")"

# LXC needs the sandbox flags; harmless elsewhere.
export CARBIDE_NO_SANDBOX=1

# Prefer the project venv if present, else system python.
PY="./.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

"$PY" scrape.py

git add data/prices.json
if git diff --cached --quiet; then
    echo "No change to commit."
    exit 0
fi
git commit -m "price: $(date +%F)"
git push
