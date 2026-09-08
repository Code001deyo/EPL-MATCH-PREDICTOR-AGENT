"""Stored title-race probabilities, one row per club per simulation run.

A simulation on its own answers "who wins the league?" once. The interesting
question is how that answer *moves* — a club's title probability climbing through
a winning run, or collapsing in a week, is the thing worth showing. That needs
history, and history needs somewhere to keep it.

So every simulation writes a snapshot, and the chart reads the series.

Two kinds of snapshot live here, and they must not be confused:

- **live** — written after a real refresh, at the time it happened. This is what
  the model said, when it said it.
- **backfill** — a reconstruction. Take the league table as it stood after some
  earlier matchweek, simulate the rest with *today's* model, and record the
  result. It exists so the chart is not empty for the first months of a season,
  and it is honestly not the same thing: the model has since been trained on
  matches that had not been played at the point being reconstructed.

`kind` is stored so the UI can draw the difference rather than quietly present a
reconstruction as a record.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text, UniqueConstraint, Index
from sqlalchemy.types import Float as Real

from db.database import Base

KIND_LIVE = "live"
KIND_BACKFILL = "backfill"


class TitleOddsSnapshot(Base):
    __tablename__ = "title_odds_snapshots"
    __table_args__ = (
        # One row per club per matchweek per kind. Re-running a backfill replaces
        # rather than accumulates; without this a repeated backfill would stack
        # duplicate points and the curve would develop invented wobble.
        UniqueConstraint("season", "matchweek", "team", "kind",
                         name="uq_title_odds_point"),
    )

    id = Column(Integer, primary_key=True, index=True)

    season = Column(Text, index=True)
    # The matchweek the table reflected when this was computed — the chart's
    # x-axis. Not the date: a date axis would bunch every point of a busy week
    # together and leave a gap over an international break.
    matchweek = Column(Integer, index=True)
    team = Column(Text, index=True)

    # Frequencies across the simulated seasons, 0..1.
    title_prob = Column(Real)
    top_four_prob = Column(Real)
    relegation_prob = Column(Real)

    # Where the club stood when this was computed, so a tooltip can say why the
    # number moved without a second query.
    points = Column(Integer)
    played = Column(Integer)
    goal_difference = Column(Integer)
    # Mean final points across the simulations — the "expected finish" line.
    projected_points = Column(Real)

    kind = Column(Text, index=True, default=KIND_LIVE)
    simulations = Column(Integer)      # how many seasons were simulated
    created_at = Column(Text)


# The chart's query: one season's series, in matchweek order.
Index("idx_title_odds_series", TitleOddsSnapshot.season, TitleOddsSnapshot.matchweek)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_snapshot(db, season: str, matchweek: int, rows: list[dict],
                  kind: str = KIND_LIVE, simulations: int = 0) -> int:
    """Write one simulation's per-club results, replacing any existing point.

    Replace rather than skip: a live snapshot recomputed after a correction to
    the underlying results should reflect the correction, not the first answer.
    """
    existing = {
        r.team: r
        for r in db.query(TitleOddsSnapshot).filter(
            TitleOddsSnapshot.season == season,
            TitleOddsSnapshot.matchweek == matchweek,
            TitleOddsSnapshot.kind == kind,
        ).all()
    }

    now = _now()
    for row in rows:
        target = existing.get(row["team"])
        if target is None:
            target = TitleOddsSnapshot(
                season=season, matchweek=matchweek, team=row["team"], kind=kind
            )
            db.add(target)
        target.title_prob = row.get("title_prob")
        target.top_four_prob = row.get("top_four_prob")
        target.relegation_prob = row.get("relegation_prob")
        target.points = row.get("points")
        target.played = row.get("played")
        target.goal_difference = row.get("goal_difference")
        target.projected_points = row.get("projected_points")
        target.simulations = simulations
        target.created_at = now

    db.commit()
    return len(rows)


def series(db, season: str, teams: list[str] | None = None) -> list[dict]:
    """The stored curve for a season, oldest matchweek first."""
    q = db.query(TitleOddsSnapshot).filter(TitleOddsSnapshot.season == season)
    if teams:
        q = q.filter(TitleOddsSnapshot.team.in_(teams))
    rows = q.order_by(TitleOddsSnapshot.matchweek.asc()).all()
    return [
        {
            "matchweek": r.matchweek,
            "team": r.team,
            "title_prob": r.title_prob,
            "top_four_prob": r.top_four_prob,
            "relegation_prob": r.relegation_prob,
            "points": r.points,
            "played": r.played,
            "projected_points": r.projected_points,
            "kind": r.kind,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def latest_matchweek(db, season: str, kind: str | None = None) -> int | None:
    from sqlalchemy import func
    q = db.query(func.max(TitleOddsSnapshot.matchweek)).filter(
        TitleOddsSnapshot.season == season
    )
    if kind:
        q = q.filter(TitleOddsSnapshot.kind == kind)
    return q.scalar()
