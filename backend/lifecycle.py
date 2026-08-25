"""Startup ingestion and periodic refresh, off the request path.

Previously the whole ingestion pipeline ran inside a synchronous
`@app.on_event("startup")` hook. Uvicorn does not accept connections until that
returns, so on a cold volume the container answered nothing for minutes and was
indistinguishable from a hung process — there was no way to ask it what it was
doing. Two of the steps were also unwrapped, so a single upstream failure
aborted boot entirely.

Ingestion now runs on a background thread. The service is live immediately
(`/health`), reports its own progress (`/health/ready`), and degrades to
"running but honestly stale" when a source is unreachable instead of dying.
"""

import os
import threading
import time
from datetime import datetime, timezone

# Ordered so a caller can tell how far a partial run got.
PHASES = ["fixtures", "statistics", "promoted-history", "settlement", "complete"]

_lock = threading.Lock()
_state = {
    "ready": False,
    "phase": "starting",
    "started_at": None,
    "completed_at": None,
    "last_refreshed": None,
    "errors": [],
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set(**kw):
    with _lock:
        _state.update(kw)


def _record_error(step, exc):
    with _lock:
        _state["errors"].append({"step": step, "error": str(exc), "at": _now()})
    print(f"[lifecycle] {step} failed: {exc}")


def status():
    """Snapshot for /health/ready. Copied under the lock so callers can't tear."""
    with _lock:
        return dict(_state, errors=list(_state["errors"]))


def last_refreshed():
    with _lock:
        return _state["last_refreshed"]


# Serialises every refresh, whoever started it: the operator endpoint, the
# in-process timer and startup ingestion all land here. Refresh deletes the
# season's rows and re-inserts them, so two overlapping runs would be reading a
# table the other one had half-emptied. The HTTP path is additionally
# single-flight through jobs.submit(), but that cannot see the timer, and the
# timer cannot see it.
_refresh_lock = threading.Lock()


def refresh_live_data():
    """Refresh the in-progress season without destroying its statistics.

    `refresh_current_season` deletes the season's rows and re-inserts them from
    PulseLive, which carries goals but no shot data. Called on its own it
    therefore *wipes* the football-data.co.uk statistics that reconciliation
    attached — the endpoint silently degraded the data it was meant to freshen.
    That was invisible at boot only because enrichment happened to run after it.

    Refresh, re-enrich and settle are one unit here, so no caller can perform
    half of it.
    """
    with _refresh_lock:
        return _refresh_live_data()


def _refresh_live_data():
    from data.ingestion import refresh_current_season, _current_season_label
    from data.reconcile import enrich_all
    from db.database import SessionLocal
    from db.settlement import settle_predictions

    season = _current_season_label()
    result = {
        "season": season,
        "played_fixtures": None,
        "enriched": None,
        "statistics_status": None,
        "settled": None,
    }

    result["played_fixtures"] = refresh_current_season()

    try:
        reports = enrich_all([season])
        # Report the matched count, not the raw report objects: the caller is an
        # HTTP response and a coverage number is what the UI can actually use.
        result["enriched"] = sum(r.get("matched", 0) or 0 for r in reports)
        result["statistics_status"] = reports[0].get("status") if reports else None
    except Exception as exc:
        _record_error("refresh:statistics", exc)

    db = SessionLocal()
    try:
        result["settled"] = settle_predictions(db)
    except Exception as exc:
        _record_error("refresh:settlement", exc)
    finally:
        db.close()

    # Reconciliation attaches statistics to rows that already exist, so the row
    # count, max id and max date are all unchanged — the cache signature would not
    # notice. Clearing explicitly is the reason enrichment cannot serve stale
    # features to the next prediction.
    from data.features import invalidate_match_cache
    invalidate_match_cache()

    _set(last_refreshed=_now())
    return result


def run_ingestion():
    """Full cold-start pipeline. Every step is isolated; a failure degrades."""
    from data.ingestion import seed_database, get_season_ids, _current_season_label
    from data.reconcile import enrich_all
    from data.promoted import ingest_efl_history
    from db.database import SessionLocal
    from db.settlement import settle_predictions

    _set(started_at=_now(), phase="fixtures", ready=False)

    # 1. Fixture spine and results from PulseLive (authoritative for what exists)
    try:
        seed_database()
    except Exception as exc:
        _record_error("fixtures:seed", exc)

    try:
        refresh_current_season_count = refresh_live_data()["played_fixtures"]
        print(f"[lifecycle] current season refreshed: {refresh_current_season_count} played fixtures")
    except Exception as exc:
        _record_error("fixtures:refresh", exc)

    # 2. Real match statistics from football-data.co.uk, joined onto that spine.
    #    The current season's file may not be published yet; that leaves stats
    #    NULL rather than failing, and NULL is passed to the model as missing.
    _set(phase="statistics")
    print("\nAttaching match statistics...")
    try:
        enrich_all(list(get_season_ids().keys()))
    except Exception as exc:
        _record_error("statistics", exc)

    # 3. Championship history for promoted clubs, so no club starts empty.
    _set(phase="promoted-history")
    print("\nBackfilling promoted-club history...")
    try:
        ingest_efl_history(_current_season_label())
    except Exception as exc:
        _record_error("promoted-history", exc)

    # 4. Settle any live predictions whose fixture has since been played, so
    #    real-user accuracy accrues without waiting for someone to open the
    #    performance dashboard.
    _set(phase="settlement")
    print("\nSettling live predictions...")
    db = SessionLocal()
    try:
        settled = settle_predictions(db)
        print(f"Settled {settled} prediction(s) against played fixtures.")
    except Exception as exc:
        _record_error("settlement", exc)
    finally:
        db.close()

    _set(phase="complete", ready=True, completed_at=_now(), last_refreshed=_now())
    print(f"[lifecycle] startup ingestion complete at {_now()}")


def _refresh_loop(interval_hours):
    """Keep the in-progress season current without needing a container restart.

    Data was previously only as fresh as the last boot: nothing re-fetched the
    live season, so a container left running for a week served week-old results.
    """
    interval = interval_hours * 3600
    while True:
        time.sleep(interval)
        try:
            print(f"[lifecycle] scheduled refresh ({interval_hours}h)")
            # Through the job store so an operator polling a refresh they started
            # sees this one rather than a second run racing it.
            import jobs
            jobs.submit("refresh", lambda _job_id: refresh_live_data())
        except Exception as exc:
            _record_error("scheduled-refresh", exc)


def start():
    """Kick off startup ingestion and, optionally, the periodic refresh."""
    threading.Thread(target=run_ingestion, name="startup-ingestion", daemon=True).start()

    try:
        hours = float(os.getenv("REFRESH_INTERVAL_HOURS", "6"))
    except ValueError:
        hours = 6.0
    if hours > 0:
        threading.Thread(
            target=_refresh_loop, args=(hours,), name="refresh-loop", daemon=True
        ).start()
        print(f"[lifecycle] periodic refresh every {hours}h")
    else:
        print("[lifecycle] periodic refresh disabled")
