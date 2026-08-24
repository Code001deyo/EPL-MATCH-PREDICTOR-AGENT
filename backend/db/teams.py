"""Which clubs the app is allowed to offer as a fixture.

`match_results` deliberately holds more than the Premier League. `data/promoted.py`
stores Championship (division "E1") matches for clubs that have just come up, so a
newly-promoted side has real prior form in its rolling features instead of NaN on
matchday one. That is a feature-engineering input, not a catalogue of selectable
teams.

Nothing enforced that distinction at the API boundary, so `GET /teams` returned 47
clubs — Wrexham, Plymouth, Millwall, Bristol City, Charlton, Oxford, QPR among them —
and users could and did submit fixtures that cannot exist. Two such rows are in the
predictions table: "Arsenal vs Coventry" and "Hull vs Man Utd".

Every endpoint that enumerates teams for a human to pick from must go through here.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.database import MatchResult

TOP_FLIGHT = "E0"


def top_flight_teams(db: Session) -> list[str]:
    """Every club with at least one Premier League appearance in the stored history.

    Both sides of the fixture are unioned: a club relegated after a single season
    still appears as a home team, but a club that only ever played away in the
    covered window would be missed by a home-only scan.
    """
    home = db.query(MatchResult.home_team).filter(MatchResult.division == TOP_FLIGHT)
    away = db.query(MatchResult.away_team).filter(MatchResult.division == TOP_FLIGHT)
    names = {r[0] for r in home.distinct().all()} | {r[0] for r in away.distinct().all()}
    names.discard(None)
    return sorted(names)


def is_top_flight(db: Session, team: str) -> bool:
    """True if this club has ever played a stored Premier League match."""
    return (
        db.query(MatchResult.id)
        .filter(
            MatchResult.division == TOP_FLIGHT,
            or_(MatchResult.home_team == team, MatchResult.away_team == team),
        )
        .first()
        is not None
    )
