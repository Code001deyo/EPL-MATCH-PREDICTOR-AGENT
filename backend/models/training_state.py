"""How far through the season the current model was trained.

Retraining has been a manual step: an operator ran the workflow when they
remembered. The model therefore sat on last month's data for as long as nobody
thought about it, and nothing on the site said so - the numbers looked exactly as
current as they always do.

This records the matchweek the model was trained through, so "is the model stale"
becomes a question with an answer rather than a guess, and a schedule can act on
it.

Kept beside `metrics.json` in the models directory rather than in the database,
because it describes the model files and must travel with them. The free tier has
no persistent disk: a deploy restores the baked seed models, and this watermark
goes back with them. That is correct, not a bug - after a deploy the running model
really is the one that was baked, and it really does need retraining.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "saved_models")
STATE_PATH = os.path.join(MODEL_DIR, "training_state.json")

# A matchweek is only "complete" once this many of its ten fixtures have been
# played. Not ten: a match postponed to midweek would otherwise hold the whole
# season's watermark back, and the nine that were played are enough new evidence
# to be worth training on.
COMPLETE_THRESHOLD = 8


def read_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        # No watermark means the model predates this, or a deploy has just
        # restored the baked seed. Either way it is stale by definition.
        return {}


def write_state(season: str, matchweek: int, extra: dict | None = None) -> dict:
    state = {
        "season": season,
        "trained_through_matchweek": matchweek,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return state


def completed_matchweek(db, season: str, division: str = "E0") -> int:
    """The highest matchweek with enough fixtures played to count as finished.

    Counted from results rather than from the calendar. A matchweek's date having
    passed does not mean its matches were played, and a model trained on fixtures
    that have not happened is trained on nothing.
    """
    from sqlalchemy import func
    from db.database import MatchResult

    rows = (
        db.query(MatchResult.matchweek, func.count(MatchResult.id))
        .filter(MatchResult.season == season,
                MatchResult.division == division,
                MatchResult.home_goals.isnot(None))
        .group_by(MatchResult.matchweek)
        .all()
    )
    complete = [int(mw) for mw, played in rows if played >= COMPLETE_THRESHOLD]
    return max(complete) if complete else 0


def staleness(db, season: str) -> dict:
    """Whether the model is behind the season, and by how much."""
    state = read_state()
    current = completed_matchweek(db, season)

    trained = state.get("trained_through_matchweek")
    same_season = state.get("season") == season
    # A watermark from a previous season does not vouch for this one.
    trained_here = trained if (same_season and isinstance(trained, int)) else None

    return {
        "season": season,
        "completed_matchweek": current,
        "trained_through_matchweek": trained_here,
        "trained_at": state.get("trained_at"),
        "behind_by": None if trained_here is None else max(0, current - trained_here),
        "stale": current > 0 and (trained_here is None or current > trained_here),
    }
