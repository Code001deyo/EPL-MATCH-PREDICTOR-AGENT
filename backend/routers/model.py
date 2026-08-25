"""Model lifecycle endpoints — retrain, trained-metrics, and the P10 backtest.

Split out of main.py to keep it under the project's ~200-line convention and
to keep "train/evaluate the model" together as one domain, separate from app
bootstrap and data-freshness reporting.
"""
import json
import os

from fastapi import APIRouter, Depends

from auth import require_admin, HTTPException, Response
from sqlalchemy.orm import Session

import jobs
from routers.outcomes import outcome_sign as _outcome_sign
from db.database import get_db, SessionLocal, Backtest
from data.features import load_matches, build_training_matrix
from models.ml_model import train, _argmax_outcome
from models.backtest import run_backtest
from models.backtest_metrics import summarize

router = APIRouter(prefix="/model")

METRICS_PATH = os.path.join(os.path.dirname(__file__), "..", "saved_models", "metrics.json")


MIN_TRAINING_MATCHES = 50


def _require_data(db, action: str):
    """Reject early, with a real status code.

    This used to return {"error": ...} with HTTP 200, so axios resolved and the
    UI took its success path for a retrain that never happened.
    """
    df = load_matches(db)
    if len(df) < MIN_TRAINING_MATCHES:
        raise HTTPException(
            status_code=409,
            detail=f"Not enough data to {action}. Have {len(df)} matches, "
                   f"need at least {MIN_TRAINING_MATCHES}.",
        )
    return df


@router.post("/retrain", status_code=202, dependencies=[Depends(require_admin)])
def retrain_model(response: Response, db: Session = Depends(get_db)):
    """Start a retrain and return immediately with a job id.

    Training fits 12 estimators over the full history and takes minutes. Held
    open as a synchronous request it gave the browser nothing to render and
    frequently outlived the browser's own timeout, so a successful retrain was
    reported to the user as a failure. Poll /model/jobs/{job_id} for progress.
    """
    _require_data(db, "train")

    def work(job_id):
        # A fresh session: the request-scoped one is closed once we return 202.
        session = SessionLocal()
        try:
            jobs.progress(job_id, stage="building feature matrix")
            matches = load_matches(session)
            # Release the transaction before the long CPU-bound work.
            #
            # Reading opens a transaction, and it stayed open for the whole
            # feature build and training run - tens of minutes. Managed Postgres
            # kills connections that sit idle inside a transaction, so the retrain
            # died with "terminating connection due to idle-in-transaction
            # timeout" after doing all the work and before saving any of it.
            #
            # Nothing below needs the database until training finishes: the
            # feature matrix is an in-memory DataFrame by this point. Ending the
            # transaction here also stops a long retrain from holding a connection
            # out of a pool that live predictions are drawing from.
            session.close()
            feature_df = build_training_matrix(matches)
            jobs.progress(job_id, stage="training", total=12)
            return {
                "samples": int(len(feature_df)),
                "metrics": train(
                    feature_df,
                    on_progress=lambda stage, done, total: jobs.progress(
                        job_id, stage=stage, done=done, total=total
                    ),
                ),
            }
        finally:
            session.close()

    job, created = jobs.submit("retrain", work)
    if not created:
        # Joined to a run already in flight rather than starting a rival that
        # would race it writing the same .pkl files.
        response.status_code = 200
    return {"job_id": job["id"], "state": job["state"], "started": created, "job": job}


@router.post("/backtest/run", status_code=202, dependencies=[Depends(require_admin)])
def backtest_run(response: Response, seasons: int = 3, db: Session = Depends(get_db)):
    """Trigger a fresh walk-forward backtest. Replaces any previously stored
    run — see models/backtest.py for what "walk-forward" means here.

    Also a job: a walk-forward run refits per matchweek and is slower than a
    single retrain.
    """
    _require_data(db, "backtest")

    def work(job_id):
        session = SessionLocal()
        try:
            jobs.progress(job_id, stage="building feature matrix")
            return run_backtest(
                session,
                seasons=seasons,
                on_progress=lambda stage, done, total: jobs.progress(
                    job_id, stage=stage, done=done, total=total
                ),
            )
        finally:
            session.close()

    job, created = jobs.submit("backtest", work)
    if not created:
        response.status_code = 200
    return {"job_id": job["id"], "state": job["state"], "started": created, "job": job}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """Progress of a retrain or backtest started above."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    return job


@router.get("/jobs")
def jobs_active():
    """Whatever is currently in flight, so a reloaded page can re-attach."""
    return {kind: jobs.active(kind) for kind in ("retrain", "backtest")}


@router.get("/backtest")
def backtest_report(season: str = None, db: Session = Depends(get_db)):
    """Headline backtested accuracy, by-season and by-matchweek breakdowns, and
    calibration buckets, read from the most recent stored run.

    `season` narrows every figure to one backtested season. Asking for a season
    the backtest did not cover returns the covered seasons rather than an empty
    chart, so the UI can say which seasons exist instead of rendering a blank
    panel that looks like a failure.
    """
    rows = db.query(Backtest).all()
    if season:
        covered = sorted({r.season for r in rows})
        rows = [r for r in rows if r.season == season]
        if not rows:
            return {
                "matches_scored": 0,
                "requested_season": season,
                "seasons_covered": covered,
                "status": "season-not-backtested",
            }
    results = [{
        "fixture_id": r.fixture_id, "season": r.season, "matchweek": r.matchweek,
        "date": r.date, "home_team": r.home_team, "away_team": r.away_team,
        "predicted_home": r.predicted_home, "predicted_away": r.predicted_away,
        "actual_home": r.actual_home, "actual_away": r.actual_away,
        "home_win_prob": r.home_win_prob, "draw_prob": r.draw_prob,
        "away_win_prob": r.away_win_prob, "confidence": r.confidence,
        # Carried so the summary can report the bookmakers' accuracy on exactly
        # these fixtures. Omitting them here silently emptied the market
        # comparison while every other figure looked fine, which is the kind of
        # missing baseline that makes an accuracy number unreadable.
        "odds_home": r.odds_home, "odds_draw": r.odds_draw, "odds_away": r.odds_away,
        # The model's actual W/D/L call is the argmax of its Poisson
        # probabilities, NOT a comparison of the rounded scoreline: two
        # near-identical lambdas (e.g. 1.6 vs 1.4) round to different
        # integers and read as a home win even when the model's own
        # probabilities called it a draw. See ml_model._outcome_accuracy for
        # the same reasoning on the live holdout.
        "predicted_outcome": _argmax_outcome(r.home_win_prob, r.draw_prob, r.away_win_prob),
        "actual_outcome": _outcome_sign(r.actual_home, r.actual_away),
    } for r in rows]
    summary = summarize(results)
    summary["run_at"] = rows[0].run_at if rows else None
    return summary


@router.get("/metrics")
def model_metrics():
    """Training metrics from the most recent retrain, for the model page."""
    if not os.path.exists(METRICS_PATH):
        return {"trained": False, "detail": "No model trained yet. POST /model/retrain."}
    with open(METRICS_PATH) as fh:
        return {"trained": True, **json.load(fh)}
