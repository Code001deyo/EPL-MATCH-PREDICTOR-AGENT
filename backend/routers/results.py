from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db, Prediction

router = APIRouter()


# POST /results was removed deliberately.
#
# It took a prediction id and a scoreline and wrote them straight into
# `actual_home`/`actual_away`, with no authentication. On a public deployment that
# is not a feature with a missing check — it is an endpoint whose only capability
# is falsifying the accuracy figures the dashboard reports. Anyone could have made
# the model look flawless or broken.
#
# Nothing legitimate needed it: actual results are derived from real match data by
# db/settlement.py, which matches a prediction to its fixture and copies the score
# that actually happened. Adding an admin guard would have preserved a capability
# with no honest use, so the endpoint is gone instead.


@router.get("/predictions/history")
def prediction_history(season: str = None, limit: int = None, db: Session = Depends(get_db)):
    """Predictions, newest first, optionally narrowed to one season.

    The season filter exists so the dashboard's selector actually drives this
    panel; without it the control was decorative here.
    """
    q = db.query(Prediction)
    if season:
        q = q.filter(Prediction.season == season)
    q = q.order_by(Prediction.created_at.desc())
    if limit:
        q = q.limit(limit)
    preds = q.all()
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
            "updated_at": p.updated_at,
            # Surfaced so a re-prediction is visible. Collapsing duplicates into
            # one row must not also erase that the fixture was predicted more
            # than once — that is information, not noise.
            "times_predicted": p.times_predicted or 1,
        }
        for p in preds
    ]}
