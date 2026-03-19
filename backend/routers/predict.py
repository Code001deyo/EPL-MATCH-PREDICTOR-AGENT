from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional
import json

from db.database import get_db, Prediction, MatchResult
from data.features import load_matches, build_feature_vector
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
def predict_fixture(req: PredictRequest, db: Session = Depends(get_db)):
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
        season = req.season or "2025-26"
        predict_date = str(date.today())
    else:
        raise HTTPException(status_code=400, detail="Provide either fixture_id or both home_team and away_team.")

    if home_team == away_team:
        raise HTTPException(status_code=400, detail="Home and away team cannot be the same.")

    df = load_matches(db)
    if df.empty:
        raise HTTPException(status_code=400, detail="No match data in database. Run ingestion first.")

    # Exclude the fixture itself when building features (no data leakage)
    if req.fixture_id is not None:
        df = df[df["id"] != req.fixture_id]

    try:
        features = build_feature_vector(df, home_team, away_team, predict_date)
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

    record = Prediction(
        fixture=f"{home_team} vs {away_team}",
        season=season,
        matchweek=matchweek,
        predicted_home=result["predicted_home"],
        predicted_away=result["predicted_away"],
        home_win_prob=result["home_win_prob"],
        draw_prob=result["draw_prob"],
        away_win_prob=result["away_win_prob"],
        confidence=result["confidence"],
        key_drivers=json.dumps(drivers),
        actual_home=fixture_row.home_goals if req.fixture_id else None,
        actual_away=fixture_row.away_goals if req.fixture_id else None,
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "fixture": record.fixture,
        "matchweek": matchweek,
        "season": season,
        "date": predict_date,
        "predicted_score": f"{result['predicted_home']}-{result['predicted_away']}",
        "home_goals": result["predicted_home"],
        "away_goals": result["predicted_away"],
        "probabilities": {
            "home_win": result["home_win_prob"],
            "draw": result["draw_prob"],
            "away_win": result["away_win_prob"],
        },
        "confidence": result["confidence"],
        "key_drivers": drivers,
        "actual_score": actual_score,
        "prediction_id": record.id,
    }
