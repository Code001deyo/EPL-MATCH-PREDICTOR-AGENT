FROM python:3.11-slim

# Hugging Face Spaces runs containers as uid 1000 and will not grant root. The
# previous image ran as root with root-owned /app, so on HF the very first write
# — creating the SQLite file — failed with EACCES and the container crash-looped.
# Creating the user here means local compose and the cloud run the same image as
# the same user, rather than "works locally, permission denied in production".
RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY requirements.txt .

# Single resolve pass; pip cache is mounted so interrupted downloads resume on retry
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout=300 --retries=10 -r requirements.txt

COPY . .

# Both are written at runtime and must be owned by the runtime user. saved_models
# is created here rather than relying on the app to mkdir it, because by then the
# process has already dropped to appuser and cannot create it under a root /app.
RUN mkdir -p saved_models dbdata && chown -R appuser:appuser /app

USER appuser

# Overridden by the platform where it injects one; the default keeps compose,
# the healthcheck below and local runs all agreeing on a single port.
ENV PORT=8000 \
    DATA_DIR=/app/dbdata \
    MODEL_DIR=/app/saved_models \
    SEED_DIR=/app/seed \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Liveness, not readiness. Seeding runs on a background thread so uvicorn answers
# /health within a second of boot; /health/ready reports 503 until the seed
# finishes. Healthchecking readiness here would keep the container marked
# unhealthy — and the frontend blocked behind depends_on — for the whole of a
# cold multi-minute seed, which is worse than serving the UI with a banner.
HEALTHCHECK --interval=15s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=5).status==200 else 1)" || exit 1

# Restores the baked snapshot onto empty storage before starting uvicorn.
ENTRYPOINT ["/app/entrypoint.sh"]
