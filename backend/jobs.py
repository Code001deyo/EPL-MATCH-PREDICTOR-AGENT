"""Single-slot background jobs for long model work.

`POST /model/retrain` used to fit 12 estimators synchronously inside the request
handler. The dominant cost is building the feature matrix — a Python loop over
every historical row, each doing a dozen full-frame pandas filters — so a
retrain runs for minutes. The browser was given no job id, no progress and no
timeout: the UI showed a greyed button reading "Training..." and, if the browser
gave up first, reported "Retrain failed." for a retrain that had in fact
succeeded and written its models.

There was also no mutual exclusion. Two retrains were observed running
concurrently in the container log, interleaved, both writing the same .pkl
files — whichever finished last won, and neither caller could tell.

One job per kind at a time. A second request joins the running job instead of
starting a rival.
"""

import threading
import traceback
import uuid
from datetime import datetime, timezone

_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_active: dict[str, str] = {}   # kind -> job_id of the in-flight job

# Terminal states, kept in one place so callers agree on what "finished" means.
DONE_STATES = {"succeeded", "failed"}

# Retain a little history so a UI that polls late still finds its job.
_MAX_JOBS = 20


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot(job):
    out = dict(job)
    out.pop("_thread", None)
    return out


def get(job_id):
    with _lock:
        job = _jobs.get(job_id)
        return _snapshot(job) if job else None


def active(kind):
    """The in-flight job for a kind, or None."""
    with _lock:
        job_id = _active.get(kind)
        job = _jobs.get(job_id) if job_id else None
        if job and job["state"] not in DONE_STATES:
            return _snapshot(job)
        return None


def progress(job_id, stage=None, done=None, total=None):
    """Called from inside the worker to report where it has got to."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if stage is not None:
            job["stage"] = stage
        if done is not None:
            job["completed"] = done
        if total is not None:
            job["total"] = total
        job["updated_at"] = _now()


def _prune():
    """Caller must hold the lock."""
    if len(_jobs) <= _MAX_JOBS:
        return
    finished = sorted(
        (j for j in _jobs.values() if j["state"] in DONE_STATES),
        key=lambda j: j.get("finished_at") or "",
    )
    for job in finished[: len(_jobs) - _MAX_JOBS]:
        _jobs.pop(job["id"], None)


def submit(kind, fn):
    """Start `fn(job_id)` on a worker thread.

    Returns (job_snapshot, created). `created` is False when an equivalent job
    was already running — the caller is joined to it rather than starting a
    second one.
    """
    with _lock:
        existing_id = _active.get(kind)
        existing = _jobs.get(existing_id) if existing_id else None
        if existing and existing["state"] not in DONE_STATES:
            return _snapshot(existing), False

        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "kind": kind,
            "state": "running",
            "stage": "starting",
            "completed": 0,
            "total": None,
            "started_at": _now(),
            "updated_at": _now(),
            "finished_at": None,
            "result": None,
            "error": None,
        }
        _jobs[job_id] = job
        _active[kind] = job_id
        _prune()

    def runner():
        try:
            result = fn(job_id)
            with _lock:
                j = _jobs[job_id]
                j.update(state="succeeded", stage="complete", result=result,
                         finished_at=_now(), updated_at=_now())
        except Exception as exc:
            traceback.print_exc()
            with _lock:
                j = _jobs[job_id]
                j.update(state="failed", error=str(exc),
                         finished_at=_now(), updated_at=_now())

    thread = threading.Thread(target=runner, name=f"job-{kind}-{job_id}", daemon=True)
    with _lock:
        _jobs[job_id]["_thread"] = thread
    thread.start()

    with _lock:
        return _snapshot(_jobs[job_id]), True
