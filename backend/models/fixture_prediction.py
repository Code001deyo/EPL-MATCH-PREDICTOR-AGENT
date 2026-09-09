"""Produce and store the one prediction a fixture is allowed to have.

Extracted from `routers/predict.py` because there is now a second caller. The
notifier has to mail a prediction before kickoff whether or not a visitor
happened to click Predict on that match, so it needs to make one — and the
`predictions` table has an invariant that only survives if a single piece of code
writes it.

That invariant: **one row per (season, "Home vs Away")**. Re-predicting updates in
place. Before it existed, clicking Predict twice put the match in History twice,
and the live database really did list "Arsenal vs Chelsea" under 2026-27 as two
separate rows from ordinary use. Two independent writers would reintroduce that
by drifting apart, which is why the upsert lives here rather than being copied.
"""

from __future__ import annotations

import json
from datetime import datetime

from data.features import load_matches, prediction_indexes
from data.vector import build_feature_vector
from db.database import Prediction
from models.ml_model import predict as run_model


def fixture_label(home_team: str, away_team: str) -> str:
    """The key settlement and the predictions table both use.

    Two clubs meet at a given ground once per campaign — verified unique across
    all 6,545 stored matches — so (season, label) identifies a fixture without
    needing an id the UI does not have.
    """
    return f"{home_team} vs {away_team}"


def predict_now(db, home_team: str, away_team: str, predict_date: str) -> dict:
    """Run the model for a fixture that has not been played.

    Only for upcoming fixtures. A historical replay has to cut the frame off
    around the match itself to avoid leaking its result, which is what the
    `fixture_id` branch in `routers/predict.py` handles; this deliberately does
    not, because a fixture that has not happened cannot leak.
    """
    df = load_matches(db)
    if df.empty:
        raise ValueError("No match data in database.")

    # The shared index is correct for a live fixture — it is cut off after every
    # stored match — and reusing it avoids rebuilding one per fixture, which
    # matters when the notifier walks a full matchday.
    index, strength = prediction_indexes(db)
    features = build_feature_vector(
        df, home_team, away_team, predict_date, strength=strength, index=index
    )
    return run_model(features)


def store_prediction(db, *, home_team: str, away_team: str, season: str,
                     matchweek: int, result: dict, drivers: list | None = None,
                     actual_home=None, actual_away=None) -> Prediction:
    """Upsert the fixture's single prediction row. The only writer of this table."""
    label = fixture_label(home_team, away_team)
    now = datetime.utcnow().isoformat()

    record = (
        db.query(Prediction)
        .filter(Prediction.season == season, Prediction.fixture == label)
        .first()
    )
    if record is None:
        record = Prediction(fixture=label, season=season, created_at=now, times_predicted=0)
        db.add(record)

    # The forecast is always replaced: a newer prediction reflects a newer model
    # and more data, so keeping the older one would be keeping the worse one.
    record.matchweek = matchweek
    record.predicted_home = result["predicted_home"]
    record.predicted_away = result["predicted_away"]
    record.home_win_prob = result["home_win_prob"]
    record.draw_prob = result["draw_prob"]
    record.away_win_prob = result["away_win_prob"]
    record.confidence = result["confidence"]
    record.key_drivers = json.dumps(drivers or [])
    record.predicted_stats = json.dumps(result.get("predicted_stats", {}))
    record.times_predicted = (record.times_predicted or 0) + 1
    record.updated_at = now

    # A settled result is never unset by a re-prediction. Overwriting it with
    # None for a fixture predicted by team name would silently un-settle a match
    # that has already been played and scored.
    if actual_home is not None or actual_away is not None:
        record.actual_home = actual_home
        record.actual_away = actual_away

    db.commit()
    db.refresh(record)
    return record


def stored_prediction(db, season: str, home_team: str, away_team: str) -> Prediction | None:
    return (
        db.query(Prediction)
        .filter(Prediction.season == season,
                Prediction.fixture == fixture_label(home_team, away_team))
        .first()
    )
