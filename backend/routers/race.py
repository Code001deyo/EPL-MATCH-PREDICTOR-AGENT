"""The title race: current probabilities, and how they have moved.

`GET /race/current` reads the most recent stored snapshot rather than simulating
on request. A simulation is 350 model calls plus ten thousand simulated seasons —
around thirty seconds — which is not a thing to do inside a page load, and doing
it per visitor would also mean two people could see two different numbers for the
same table. One simulation per refresh, read many times.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

import jobs
from auth import require_admin
from data.ingestion import _current_season_label
from db.database import SessionLocal
from db import race as race_db

router = APIRouter(prefix="/race", tags=["race"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/current")
def current(season: str = None, db: Session = Depends(get_db)):
    """Latest per-club title, top-four and relegation probabilities.

    Also carries the change since the previous matchweek. That delta is the
    number that makes the page feel alive, and computing it here means the client
    does not have to fetch and diff the whole series to show one arrow.
    """
    season = season or _current_season_label()
    latest = race_db.latest_matchweek(db, season)
    if latest is None:
        # Honest empty state, not a page of zeros. Zeros would read as "every
        # club has no chance", which is a claim; "not simulated yet" is the fact.
        return {"season": season, "status": "not-simulated", "teams": []}

    rows = race_db.series(db, season)
    now = [r for r in rows if r["matchweek"] == latest]
    previous = {r["team"]: r for r in rows if r["matchweek"] == latest - 1}

    teams = []
    for row in sorted(now, key=lambda r: (-(r["title_prob"] or 0), -(r["points"] or 0))):
        before = previous.get(row["team"])
        teams.append({
            **row,
            # None, not 0.0, when there is nothing to compare against. A first
            # matchweek has no movement; showing 0.0 would claim it held steady.
            "title_delta": (
                None if before is None
                else round((row["title_prob"] or 0) - (before["title_prob"] or 0), 4)
            ),
        })

    return {
        "season": season,
        "status": "ok",
        "matchweek": latest,
        "teams": teams,
        # The UI needs this to caption the chart honestly — see db/race.py.
        "kind": teams[0]["kind"] if teams else None,
    }


@router.get("/history")
def history(season: str = None, team: str = Query(None),
            db: Session = Depends(get_db)):
    """The stored series behind the curve."""
    season = season or _current_season_label()
    teams = [team] if team else None
    return {"season": season, "points": race_db.series(db, season, teams=teams)}


@router.post("/simulate", status_code=202, dependencies=[Depends(require_admin)])
def simulate(response: Response, simulations: int = 10_000,
             backfill: bool = False):
    """Re-run the simulation. Admin-only: it is thirty seconds of CPU.

    `backfill=true` also reconstructs every completed matchweek. That is a
    reconstruction by today's model, stored and labelled as one.
    """
    def work(job_id):
        from models import season_history, season_sim

        db = SessionLocal()
        try:
            season = _current_season_label()

            def progress(done, total):
                jobs.progress(job_id, stage="pricing fixtures", done=done,
                              total=total, unit="fixtures")

            out = season_sim.run(db, season, simulations=simulations,
                                 on_progress=progress)
            if out["status"] != "ok":
                return out

            jobs.progress(job_id, stage="saving")
            # Stamped at the moment the matchweek finished, not at the moment
            # this ran. Two simulations of the same matchweek must land on the
            # same point of the time axis, or re-running the job would slide the
            # curve sideways and invent movement.
            ends = season_history.matchweek_ended_at(db, season)
            race_db.save_snapshot(db, season, out["matchweek"], out["teams"],
                                  kind=race_db.KIND_LIVE, simulations=simulations,
                                  as_of=ends.get(out["matchweek"]))

            if backfill:
                jobs.progress(job_id, stage="reconstructing earlier matchweeks")
                out["backfill"] = season_history.backfill(db, season)

            # The teams list is dropped from the job result: it is already stored
            # and readable at /race/current, and a job payload is not the place
            # for a twenty-row table.
            return {k: v for k, v in out.items() if k != "teams"}
        finally:
            db.close()

    job, created = jobs.submit("season_sim", work)
    if not created:
        response.status_code = 200
    return {"job_id": job["id"], "state": job["state"], "started": created, "job": job}


@router.get("/jobs/{job_id}")
def race_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    return job
