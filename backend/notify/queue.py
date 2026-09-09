"""Which notifications are due right now.

Separated from the sending in `dispatch.py` because the two answer different
questions and the timing rules are the part worth reading on their own: what
counts as "before kickoff", how long a match occupies, and what evidence is
required before claiming a match has finished.

All of it lives in the API rather than in the cron. GitHub Actions cron drifts
five to fifteen minutes on public runners and the Render instance sleeps between
visits, so a trigger cannot be trusted to fire at a wall-clock moment; it can only
be trusted to ask, often enough, what is due. The consequence is stated rather
than hidden: a pre-match email arrives in a window before kickoff, not exactly ten
minutes before.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from db.fixtures import Fixture

PRE_WINDOW_MINUTES = int(os.environ.get("NOTIFY_PRE_WINDOW_MINUTES", "20"))

# A Premier League match occupies about 115 minutes of wall clock: 90 played,
# 15 at half time, plus stoppage. The post-match email waits for that plus a
# margin, and *also* for the result to actually be in the database - the wait is
# a filter for which fixtures to look at, never the evidence a match has finished.
MATCH_MINUTES = 115
POST_DELAY_MINUTES = int(os.environ.get("NOTIFY_POST_DELAY_MINUTES", "10"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def due_pre_match(db, now: datetime | None = None) -> list[Fixture]:
    """Fixtures kicking off soon that have not been mailed about.

    Fixtures with no published kickoff time are excluded by the query itself -
    `kickoff_utc` is NULL for those, and a guessed time would mail people about a
    match at the wrong moment.
    """
    now = now or _now()
    horizon = now + timedelta(minutes=PRE_WINDOW_MINUTES)

    rows = (
        db.query(Fixture)
        .filter(Fixture.kickoff_utc.isnot(None), Fixture.status == "U")
        .filter(Fixture.kickoff_utc <= horizon.isoformat())
        .filter(Fixture.kickoff_utc >= now.isoformat())
        .order_by(Fixture.kickoff_utc.asc())
        .all()
    )
    return rows


def due_post_match(db, now: datetime | None = None) -> list[tuple[Fixture, int, int]]:
    """Finished fixtures whose result is known and not yet mailed.

    Two conditions, and both are required. Enough time has passed *and* the score
    is in `match_results` - a refresh may not have run yet, and mailing "the match
    has finished" with no score in hand would be worse than waiting.
    """
    from db.database import MatchResult

    now = now or _now()
    latest_kickoff = now - timedelta(minutes=MATCH_MINUTES + POST_DELAY_MINUTES)

    candidates = (
        db.query(Fixture)
        .filter(Fixture.kickoff_utc.isnot(None))
        .filter(Fixture.kickoff_utc <= latest_kickoff.isoformat())
        # Only look back a couple of days. Without this the query re-examines
        # every fixture played all season on every five-minute tick, and a
        # backlog that old is not a notification anyone wants anyway.
        .filter(Fixture.kickoff_utc >= (now - timedelta(days=2)).isoformat())
        .all()
    )

    due = []
    for fixture in candidates:
        result = (
            db.query(MatchResult)
            .filter(
                MatchResult.season == fixture.season,
                MatchResult.home_team == fixture.home_team,
                MatchResult.away_team == fixture.away_team,
            )
            .first()
        )
        if result is None or result.home_goals is None or result.away_goals is None:
            continue                      # played, but the result has not landed yet
        due.append((fixture, result.home_goals, result.away_goals))
    return due


