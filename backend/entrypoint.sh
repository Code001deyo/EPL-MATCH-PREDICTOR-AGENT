#!/bin/sh
# Restore the baked snapshot onto empty storage, then hand off to uvicorn.
#
# Why this exists: the free hosting this deploys to (Hugging Face Spaces) gives
# the container no persistent disk. Every restart would otherwise come up with an
# empty database and no trained model, which means several minutes of re-seeding
# from the Premier League API and a /predict that answers 503 until somebody
# noticed and retrained by hand. Baking a snapshot into the image turns that into
# a restart.
#
# The guard is "is it empty", never "overwrite". On a host that DOES have a
# volume — the local docker compose setup, or any paid tier — whatever is already
# there is newer than the image and must win. A restore that clobbered a live
# database with a build-time snapshot would be a data-loss bug, and it would look
# exactly like a successful boot.
set -e

DATA_DIR="${DATA_DIR:-/app/dbdata}"
MODEL_DIR="${MODEL_DIR:-/app/saved_models}"
SEED_DIR="${SEED_DIR:-/app/seed}"

mkdir -p "$DATA_DIR" "$MODEL_DIR"

if [ ! -f "$DATA_DIR/epl.db" ] && [ -f "$SEED_DIR/epl.db" ]; then
    echo "[entrypoint] no database at $DATA_DIR/epl.db — restoring baked snapshot"
    cp "$SEED_DIR/epl.db" "$DATA_DIR/epl.db"
else
    echo "[entrypoint] existing database kept at $DATA_DIR/epl.db"
fi

# Models are restored only when NO model is present. A partial set is left alone:
# mixing a baked model with a freshly trained one would serve predictions from two
# different training runs and there would be nothing in the output to show it.
if [ -d "$SEED_DIR/models" ] && [ -z "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]; then
    echo "[entrypoint] no trained models in $MODEL_DIR — restoring baked models"
    cp "$SEED_DIR"/models/* "$MODEL_DIR"/
else
    echo "[entrypoint] existing models kept in $MODEL_DIR"
fi

# HF Spaces routes to $PORT; compose and local runs default to 8000.
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
