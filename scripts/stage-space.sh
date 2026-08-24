#!/usr/bin/env bash
# Build the exact directory tree that becomes the Hugging Face Space.
#
# Shared deliberately. The CI workflow and the manual deploy script BOTH call
# this, so the thing you push by hand and the thing CI pushes are byte-identical.
# Two separate copies of "assemble the Space" is how a manual deploy starts
# working and the automated one quietly stops.
#
# Usage: stage-space.sh <output-dir>
set -euo pipefail

OUT="${1:?usage: stage-space.sh <output-dir>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "$OUT"
mkdir -p "$OUT"

# HF expects the Dockerfile at the repo root, so the backend subtree becomes the
# Space root rather than the whole repository being pushed.
cp -r "$ROOT/backend/." "$OUT/"

# Never ship local build residue or a developer's working database.
rm -rf "$OUT/__pycache__" "$OUT/.pytest_cache" "$OUT/dbdata" "$OUT/.venv"
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$OUT" -name '*.pyc' -delete 2>/dev/null || true

# The seed snapshot is the reason a Space with no persistent disk comes up working.
# Its absence is a silent, delayed failure — the Space boots, then answers 503 on
# /predict — so it is checked here rather than discovered in production.
if [ ! -f "$OUT/seed/epl.db" ]; then
    echo "error: backend/seed/epl.db is missing; the Space would boot with no data" >&2
    exit 1
fi
if ! ls "$OUT"/seed/models/*.pkl >/dev/null 2>&1; then
    echo "error: backend/seed/models/*.pkl are missing; the Space would boot untrained" >&2
    exit 1
fi

# Space configuration lives in README frontmatter. app_port must match the port
# the Dockerfile's entrypoint binds.
cat > "$OUT/README.md" <<'EOF'
---
title: EPL Predictor API
emoji: ⚽
colorFrom: purple
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# EPL Predictor API

FastAPI + XGBoost backend for the EPL Score Predictor.

Deployed automatically from
[Code001deyo/EPL-MATCH-PREDICTOR-AGENT](https://github.com/Code001deyo/EPL-MATCH-PREDICTOR-AGENT).

**Do not edit this Space directly** — it mirrors `main` and every file here is
replaced on the next deploy.

## Endpoints

- `GET /health` — liveness
- `GET /health/ready` — 503 until the initial data load finishes
- `GET /docs` — full OpenAPI reference
EOF

echo "staged $(find "$OUT" -type f | wc -l) files into $OUT"
