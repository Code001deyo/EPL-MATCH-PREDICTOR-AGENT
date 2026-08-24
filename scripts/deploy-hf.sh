#!/usr/bin/env bash
# Deploy the backend to a Hugging Face Space from your machine.
#
#   ./scripts/deploy-hf.sh <owner>/<space-name>
#
# Use this for the first deploy — it creates the Space — and any time you want to
# push without going through GitHub. CI does the same thing on every push to main
# via .github/workflows/deploy-backend.yml, staging the tree with the same
# scripts/stage-space.sh so the two paths cannot drift.
#
# The token is read from an existing `hf auth login` session or $HF_TOKEN. This
# script never asks you to paste one and never writes one to disk.
set -euo pipefail

SPACE="${1:-${HF_SPACE:-}}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="${TMPDIR:-/tmp}/epl-space-$$"

die() { echo "error: $*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
[ -n "$SPACE" ] || die "usage: $0 <owner>/<space-name>   (or set HF_SPACE)"
case "$SPACE" in
    */*) ;;
    *) die "space must be '<owner>/<space-name>', got '$SPACE'" ;;
esac

if ! command -v hf >/dev/null 2>&1; then
    # The CLI was renamed from `huggingface-cli` to `hf`. Say so, because the old
    # name still exists on older installs and silently lacks these subcommands.
    if command -v huggingface-cli >/dev/null 2>&1; then
        die "found the old 'huggingface-cli'. Upgrade with:  pip install -U huggingface_hub"
    fi
    die "the 'hf' CLI is not installed. Install it with:  pip install -U huggingface_hub"
fi

if ! WHOAMI="$(hf auth whoami 2>/dev/null)"; then
    die "not logged in to Hugging Face. Run:  hf auth login   (or export HF_TOKEN=...)"
fi
echo "==> authenticated as: ${WHOAMI%%$'\n'*}"

# ---------------------------------------------------------------- create
# `hf repo create` fails when the Space already exists, which is the normal case
# on every deploy after the first — so a failure here is only fatal if the Space
# genuinely is not reachable afterwards.
echo "==> ensuring Space $SPACE exists"
hf repo create "$SPACE" --repo-type space --space-sdk docker -y >/dev/null 2>&1 \
    || echo "    (already exists, or creation declined — continuing)"

# ---------------------------------------------------------------- stage
echo "==> staging"
bash "$ROOT/scripts/stage-space.sh" "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

# ---------------------------------------------------------------- upload
echo "==> uploading to $SPACE"
hf upload "$SPACE" "$STAGE" . --repo-type space \
    --commit-message "Deploy from $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%dT%H%M%SZ)"

# ---------------------------------------------------------------- verify
# A finished upload is not a working deploy: HF still has to build the image, and
# a build failure looks exactly like a successful push from here.
HOST="https://$(echo "$SPACE" | tr '/' '-' | tr '[:upper:]' '[:lower:]').hf.space"
echo "==> waiting for $HOST/health (HF builds the image now; first build takes several minutes)"

for i in $(seq 1 80); do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HOST/health" || true)"
    if [ "$CODE" = "200" ]; then
        echo
        echo "LIVE  $HOST"
        curl -s "$HOST/health"; echo
        echo
        echo "Next: put this host in frontend/vercel.json, replacing REPLACE-ME:"
        echo "  \"destination\": \"$HOST/:path*\""
        exit 0
    fi
    printf '    %02d/80  HTTP %s\r' "$i" "$CODE"
    sleep 15
done

echo
die "$HOST/health did not answer within 20 minutes. Check the build logs at https://huggingface.co/spaces/$SPACE"
