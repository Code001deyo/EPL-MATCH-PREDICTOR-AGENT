"""Settlement for live (user-made) predictions.

`predictions` rows are written whenever someone clicks Predict in the UI, most
of them for fixtures that had not been played yet. Once the real match is
played and `match_results` has the score, this fills `actual_home` /
`actual_away` so live accuracy accrues on its own instead of staying stuck at
"0 evaluated". Distinct from the walk-forward backtest in models/backtest.py:
this measures what real users' predictions get, not a systematic simulation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from db.database import Prediction, MatchResult


def settle_predictions(db: Session) -> int:
    """Match unsettled predictions to their played fixture and fill the result.

    Matched on `(season, home_team, away_team)` within the top flight. A
    prediction's `fixture` field is stored as "Home vs Away" text, so it is
    split back into the two names rather than joined on an id the table
    doesn't carry.

    Matchweek is deliberately NOT part of the key. It used to be, and it is why
    `Bournemouth vs Man Utd` (2025-26) sat pending forever: the prediction was
    submitted as MW35 while ingestion had stored the fixture at MW31, so the
    join found nothing and the row was never settled even though the match had
    been played and the score was sitting in the same table.

    Dropping it is safe, not a loosening: a given (season, home, away) triple
    occurs exactly once — verified across all 2,849 stored rows in both
    divisions — because two clubs meet at a given ground once per campaign. So
    matchweek added no identifying power at all, while being the one field
    likely to disagree between what the UI submitted and what ingestion
    recorded. Do not reinstate it.

    The `division == "E0"` filter matters for the same reason: `promoted.py`
    stores Championship (E1) matches for promoted clubs, so without it a
    prediction could settle against a second-tier result.
    """
    unsettled = db.query(Prediction).filter(Prediction.actual_home.is_(None)).all()
    settled = 0
    for p in unsettled:
        if not p.fixture or " vs " not in p.fixture:
            continue
        home_team, away_team = p.fixture.split(" vs ", 1)
        match = (
            db.query(MatchResult)
            .filter(
                MatchResult.home_team == home_team,
                MatchResult.away_team == away_team,
                MatchResult.season == p.season,
                MatchResult.division == "E0",
            )
            .first()
        )
        # A played fixture has goals recorded; an unplayed one (still upcoming,
        # or a postponed match not yet rescheduled) is left alone rather than
        # settled with a fabricated result.
        if match is None or match.home_goals is None or match.away_goals is None:
            continue
        p.actual_home = match.home_goals
        p.actual_away = match.away_goals
        # Correct the matchweek to the fixture's own. The prediction carries
        # whatever the caller submitted, which is exactly the field that was
        # wrong in the case above — leaving it alone would settle the row
        # correctly but keep History displaying "MW35" for a match played in
        # MW31.
        if match.matchweek is not None and p.matchweek != match.matchweek:
            p.matchweek = match.matchweek
        settled += 1

    if settled:
        db.commit()
    return settled
