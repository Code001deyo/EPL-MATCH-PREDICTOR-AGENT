from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db, Prediction

router = APIRouter()


class ActualResult(BaseModel):
    prediction_id: int
    actual_home: int
    actual_away: int


@router.post("/results")
def submit_result(body: ActualResult, db: Session = Depends(get_db)):
    pred = db.query(Prediction).filter(Prediction.id == body.prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    pred.actual_home = body.actual_home
    pred.actual_away = body.actual_away
    db.commit()
    correct_score = pred.predicted_home == body.actual_home and pred.predicted_away == body.actual_away
    pred_result = "H" if pred.predicted_home > pred.predicted_away else ("D" if pred.predicted_home == pred.predicted_away else "A")
    actual_result = "H" if body.actual_home > body.actual_away else ("D" if body.actual_home == body.actual_away else "A")
    return {
        "updated": True,
        "correct_score": correct_score,
        "correct_result": pred_result == actual_result,
    }


@router.get("/predictions/history")
def prediction_history(db: Session = Depends(get_db)):
    preds = db.query(Prediction).order_by(Prediction.created_at.desc()).all()
    return {"predictions": [
        {
            "id": p.id,
            "fixture": p.fixture,
            "season": p.season,
            "matchweek": p.matchweek,
            "predicted": f"{p.predicted_home}-{p.predicted_away}",
            "actual": f"{p.actual_home}-{p.actual_away}" if p.actual_home is not None else None,
            "home_win_prob": p.home_win_prob,
            "draw_prob": p.draw_prob,
            "away_win_prob": p.away_win_prob,
            "confidence": p.confidence,
            "created_at": p.created_at,
        }
        for p in preds
    ]}
