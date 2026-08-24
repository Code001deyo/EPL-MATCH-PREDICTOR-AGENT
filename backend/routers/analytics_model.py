"""Model-performance analytics — split out of routers/analytics.py (P10) so
the two accuracy stories, live-settled and backtested, have room to be kept
visibly separate rather than folded into the general league/team analytics
file.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db, Prediction, Backtest
from models.backtest_metrics import summarize as summarize_backtest
from models.ml_model import _argmax_outcome

from routers.outcomes import result_letter as _result, outcome_sign as _outcome_sign

router = APIRouter(prefix="/analytics")


@router.get("/model/performance")
def model_performance(db: Session = Depends(get_db)):
    preds = db.query(Prediction).order_by(Prediction.created_at).all()
    total = len(preds)
    evaluated = [p for p in preds if p.actual_home is not None]

    exact = sum(1 for p in evaluated if p.predicted_home == p.actual_home and p.predicted_away == p.actual_away)
    correct_result = sum(1 for p in evaluated if _result(p.predicted_home, p.predicted_away) == _result(p.actual_home, p.actual_away))
    wrong = len(evaluated) - correct_result

    by_month = defaultdict(lambda: {"total": 0, "exact": 0, "correct_result": 0})
    for p in evaluated:
        month = (p.created_at or "")[:7]
        by_month[month]["total"] += 1
        if p.predicted_home == p.actual_home and p.predicted_away == p.actual_away:
            by_month[month]["exact"] += 1
        if _result(p.predicted_home, p.predicted_away) == _result(p.actual_home, p.actual_away):
            by_month[month]["correct_result"] += 1

    monthly = [
        {
            "month": m,
            "total": v["total"],
            "exact_score_pct": round(v["exact"] / v["total"], 3) if v["total"] else 0,
            "correct_result_pct": round(v["correct_result"] / v["total"], 3) if v["total"] else 0,
        }
        for m, v in sorted(by_month.items())
    ]

    avg_conf = round(sum(p.confidence or 0 for p in preds) / total, 3) if total else 0

    # Two separate figures, deliberately not blended: live-settled accuracy is
    # whatever fixtures users happened to click Predict on (self-selected,
    # mostly upcoming games that never settle); backtested accuracy is a
    # systematic walk-forward simulation over every completed matchweek. A
    # single averaged number would hide which of the two is actually measuring
    # the model.
    bt_rows = db.query(Backtest).all()
    bt_results = [{
        "season": r.season, "matchweek": r.matchweek,
        "predicted_home": r.predicted_home, "predicted_away": r.predicted_away,
        "actual_home": r.actual_home, "actual_away": r.actual_away,
        "home_win_prob": r.home_win_prob, "draw_prob": r.draw_prob,
        "away_win_prob": r.away_win_prob,
        # Argmax of the stored probabilities, not the rounded scoreline — see
        # routers/model.py for why the two disagree on close calls.
        "predicted_outcome": _argmax_outcome(r.home_win_prob, r.draw_prob, r.away_win_prob),
        "actual_outcome": _outcome_sign(r.actual_home, r.actual_away),
    } for r in bt_rows]
    backtested = summarize_backtest(bt_results)

    return {
        "live_settled": {
            "total_predictions": total,
            "evaluated": len(evaluated),
            "exact_score_count": exact,
            "correct_result_count": correct_result,
            "wrong_count": wrong,
            "exact_score_accuracy": round(exact / max(len(evaluated), 1), 3),
            "correct_result_accuracy": round(correct_result / max(len(evaluated), 1), 3),
            "avg_confidence": avg_conf,
            "by_month": monthly,
            "note": "Self-selected: whatever fixtures users predicted, mostly upcoming and not yet settled.",
        },
        "backtested": {
            **backtested,
            "note": "Systematic walk-forward simulation over every completed matchweek. See GET /model/backtest for the full breakdown.",
        },
        # Legacy top-level fields kept for callers that read the pre-P10 shape;
        # they mirror live_settled and must not be read as the whole picture.
        "total_predictions": total,
        "evaluated": len(evaluated),
        "exact_score_accuracy": round(exact / max(len(evaluated), 1), 3),
        "correct_result_accuracy": round(correct_result / max(len(evaluated), 1), 3),
    }
