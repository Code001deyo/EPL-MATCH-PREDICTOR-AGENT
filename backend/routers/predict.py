from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional
import json

from db.database import get_db, Prediction, MatchResult
from db.teams import is_top_flight
from ratelimit import limit
import pandas as pd

from data.features import load_matches, build_feature_vector
from data.odds import upcoming_odds
from data.ingestion import _current_season_label
from models.ml_model import predict, get_feature_importance

router = APIRouter()


class PredictRequest(BaseModel):
    fixture_id: Optional[int] = None      # DB id — played fixture (backtesting)
    home_team: Optional[str] = None       # custom or upcoming fixture by team names
    away_team: Optional[str] = None
    matchweek: Optional[int] = None
    season: Optional[str] = None
    kickoff: Optional[str] = None         # display only, from upcoming fixtures


@router.post("/predict")
def predict_fixture(req: PredictRequest, request: Request, db: Session = Depends(get_db)):
    # Public endpoint on an ephemeral disk: without a brake, one script fills
    # the database and saturates a 0.1 vCPU instance. Generous enough that a
    # person clicking through fixtures never notices.
    limit(request, "predict", capacity=30, per_seconds=60)
    # Resolve fixture from DB if fixture_id provided
    if req.fixture_id is not None:
        fixture_row = db.query(MatchResult).filter(MatchResult.id == req.fixture_id).first()
        if not fixture_row:
            raise HTTPException(status_code=404, detail=f"Fixture ID {req.fixture_id} not found.")
        home_team = fixture_row.home_team
        away_team = fixture_row.away_team
        matchweek = fixture_row.matchweek
        season = fixture_row.season
        # Use the day before the fixture so we don't leak its own result into features
        predict_date = fixture_row.date
    elif req.home_team and req.away_team:
        home_team = req.home_team
        away_team = req.away_team
        matchweek = req.matchweek or 1
        season = req.season or _current_season_label()
        predict_date = str(date.today())
    else:
        raise HTTPException(status_code=400, detail="Provide either fixture_id or both home_team and away_team.")

    if home_team == away_team:
        raise HTTPException(status_code=400, detail="Home and away team cannot be the same.")

    # Reject fixtures that cannot exist. `match_results` holds Championship rows
    # for promoted clubs (see db/teams.py), and until /teams was filtered the UI
    # offered them: the predictions table still contains "Arsenal vs Coventry".
    # Refusing here is the honest answer — the model is trained on top-flight
    # matches only, so a prediction for a second-tier club is a number the data
    # does not support, not a harmless extra feature.
    for side, name in (("home", home_team), ("away", away_team)):
        if not is_top_flight(db, name):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{name} has no Premier League matches in the stored history, so it "
                    f"cannot be the {side} side of a prediction. The model is trained on "
                    f"top-flight fixtures only."
                ),
            )

    df = load_matches(db)
    if df.empty:
        raise HTTPException(status_code=400, detail="No match data in database. Run ingestion first.")

    # Exclude the fixture itself when building features (no data leakage)
    if req.fixture_id is not None:
        df = df[df["id"] != req.fixture_id]

    # The fixture's own pre-match price, if a bookmaker has published one. The
    # model is trained with odds among its features, so omitting them here would
    # leave it guessing on its strongest input at exactly the moment it is asked
    # to work. Two places to look, in order:
    #
    #   1. the stored row, when this fixture is already in the database with a
    #      closing price attached (a replayed or historical prediction);
    #   2. the live upcoming-fixtures feed, for a match not yet played.
    #
    # Neither is required. `upcoming_odds` swallows its own network failures and
    # a missing price becomes NaN features, which the model handles as a real
    # condition rather than a fabricated even-money prior.
    odds = None
    stored = df[(df["home_team"] == home_team) & (df["away_team"] == away_team)]
    if not stored.empty:
        row = stored.iloc[-1]
        if pd.notna(row.get("odds_home")):
            odds = (row.get("odds_home"), row.get("odds_draw"), row.get("odds_away"))
    if odds is None:
        odds = upcoming_odds(home_team, away_team)

    try:
        features = build_feature_vector(df, home_team, away_team, predict_date, odds=odds)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = predict(features)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        importance = get_feature_importance()
        drivers = [f"{k}: {v:.3f}" for k, v in importance["home_model_top_features"][:3]]
    except Exception:
        drivers = []

    # If this is a known fixture, attach the actual score for instant comparison
    actual_score = None
    if req.fixture_id is not None and fixture_row:
        actual_score = f"{fixture_row.home_goals}-{fixture_row.away_goals}"

    # ONE prediction per fixture. Re-predicting updates the existing row rather
    # than appending a new one — before this, clicking Predict on the same match
    # twice put it in History twice, and the live database had "Arsenal vs Chelsea"
    # listed under 2026-27 two separate times from ordinary use.
    #
    # The key matches settlement's: (season, fixture). Two clubs meet at a given
    # ground once per campaign, verified unique across all 6,545 stored matches.
    fixture_label = f"{home_team} vs {away_team}"
    now = datetime.utcnow().isoformat()

    record = (
        db.query(Prediction)
        .filter(Prediction.season == season, Prediction.fixture == fixture_label)
        .first()
    )
    created = record is None
    if created:
        record = Prediction(
            fixture=fixture_label,
            season=season,
            created_at=now,
            times_predicted=0,
        )
        db.add(record)

    # The forecast itself is always replaced: a newer prediction reflects a newer
    # model and more data, so keeping the older one would be keeping the worse one.
    record.matchweek = matchweek
    record.predicted_home = result["predicted_home"]
    record.predicted_away = result["predicted_away"]
    record.home_win_prob = result["home_win_prob"]
    record.draw_prob = result["draw_prob"]
    record.away_win_prob = result["away_win_prob"]
    record.confidence = result["confidence"]
    record.key_drivers = json.dumps(drivers)
    record.predicted_stats = json.dumps(result.get("predicted_stats", {}))
    record.times_predicted = (record.times_predicted or 0) + 1
    record.updated_at = now

    # A settled result is never unset by a re-prediction. Overwriting it with None
    # for a fixture predicted by team name would silently un-settle a match that
    # has already been played and scored.
    if req.fixture_id is not None and fixture_row is not None:
        record.actual_home = fixture_row.home_goals
        record.actual_away = fixture_row.away_goals

    db.commit()
    db.refresh(record)

    return {
        "fixture": record.fixture,
        "matchweek": matchweek,
        "season": season,
        "date": predict_date,
        "predicted_score": f"{result['predicted_home']}-{result['predicted_away']}",
        # What the model actually decided. The scoreline agrees with it by
        # construction, but it is stated rather than left to the client to infer
        # by comparing two integers - which is how the site came to display a
        # draw for fixtures the model gave to the home side.
        "predicted_outcome": result["predicted_outcome"],
        "home_goals": result["predicted_home"],
        "away_goals": result["predicted_away"],
        "probabilities": {
            "home_win": result["home_win_prob"],
            "draw": result["draw_prob"],
            "away_win": result["away_win_prob"],
        },
        "confidence": result["confidence"],
        "key_drivers": drivers,
        "predicted_stats": result.get("predicted_stats", {}),
        "actual_score": actual_score,
        "prediction_id": record.id,
        # What this prediction actually rests on. A newly promoted club has no
        # Premier League record, so its forecast comes from adjusted Championship
        # form — the interface says so rather than presenting both alike.
        "home_team": home_team,
        "away_team": away_team,
        "evidence": {
            "home_top_flight_matches": _as_int(features.get("home_top_flight_matches")),
            "away_top_flight_matches": _as_int(features.get("away_top_flight_matches")),
            "home_is_newly_promoted": bool(features.get("home_is_newly_promoted")),
            "away_is_newly_promoted": bool(features.get("away_is_newly_promoted")),
        },
    }


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
