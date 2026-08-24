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

Every endpoint that enumerates teams for a human to pick from, or that reports a
figure to a human, must go through here. The `/teams` leak was fixed first and the
analytics router was not audited in the same pass, so the identical bug survived
there: the league table blended both divisions and ranked Coventry first in the
Premier League on 46 games played. Hence `division_filter` below — one boundary,
applied everywhere, rather than a filter remembered per handler.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.database import MatchResult

TOP_FLIGHT = "E0"      # Premier League
CHAMPIONSHIP = "E1"    # stored for promoted-club form only — see promoted.py

DIVISIONS = {
    TOP_FLIGHT: "Premier League",
    CHAMPIONSHIP: "Championship",
}


def division_name(division: str) -> str:
    return DIVISIONS.get(division, division)


def resolve_division(division: str | None) -> str:
    """Validate a division parameter, or raise 400.

    An unknown division used to fall straight through to `WHERE division = 'E7'`,
    match nothing, and return "no played matches for this season and division" —
    a response indistinguishable from a season that genuinely has no data. A UI
    that sent an empty string (a select rendered before its options had loaded)
    therefore showed empty cards with no error anywhere, which is exactly the
    "plausible-looking wrong answer" this codebase keeps having to dig out.

    Empty or missing means "not specified", which is the default. Anything else
    must be a division that exists.
    """
    from fastapi import HTTPException

    if not division:
        return TOP_FLIGHT
    if division == "all" or division in DIVISIONS:
        return division
    raise HTTPException(
        status_code=400,
        detail=f"Unknown division {division!r}. Valid values: {sorted(DIVISIONS)} or 'all'.",
    )


def division_filter(query, division: str = TOP_FLIGHT):
    """Restrict a MatchResult query to one division.

    `division="all"` opts out explicitly, which is the only way to get blended
    figures — previously it was the accidental default everywhere.

    Rows written before the `division` column existed are NULL, and NULL fails an
    equality test in SQL, so those rows would silently vanish from every report.
    They are top-flight, so NULL is coalesced to E0 rather than filtered out.
    """
    if division == "all":
        return query
    if division == TOP_FLIGHT:
        return query.filter(
            or_(MatchResult.division == TOP_FLIGHT, MatchResult.division.is_(None))
        )
    return query.filter(MatchResult.division == division)


def is_played(match) -> bool:
    """A fixture with no score is scheduled, not a 0-0.

    Aggregates that compare `home_goals > away_goals` raise TypeError on None in
    Python 3, so this is a crash guard as much as a correctness one.
    """
    return match.home_goals is not None and match.away_goals is not None


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
