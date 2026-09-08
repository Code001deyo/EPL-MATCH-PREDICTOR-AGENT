"""Scheduled fixtures, with a real kickoff instant.

Why this is its own table rather than more columns on `match_results`:

`match_results` holds matches that have been *played*. `ingestion.refresh_current_season`
filters to `df["home_goals"].notna()` before it writes, and deliberately so — the
whole delete-and-reinsert dance around it is guarded by rules about never
destroying stored results (see the comments there, and `tests/test_refresh_safety.py`).
An unplayed fixture has no result to protect and a different lifecycle: it appears,
its kickoff moves, and eventually it becomes a row in `match_results` instead.
Mixing the two would mean widening the one delete path this project has already
lost a season to.

Upcoming fixtures were previously never stored at all — `routers/teams.upcoming_fixtures`
fetches them live from PulseLive on every request. Two things need them persisted:

- **Notifications.** A pre-match alert has to know exactly when kickoff is, and has
  to have a stable id to record "already sent" against. PulseLive publishes
  `kickoff.millis`; `_parse_fixture` was reading it and throwing it away, keeping
  only the `YYYY-MM-DD` date.
- **The title race.** Simulating the rest of the season needs the list of matches
  still to be played.

Kickoff is nullable on purpose. The Premier League publishes fixtures before their
times are fixed, and a fixture whose kickoff is genuinely unknown must read as
unknown rather than be given a guessed 15:00 — a guess here would mail people at
the wrong time and would be indistinguishable from a real time downstream.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text, Index

from db.database import Base

# PulseLive fixture statuses that mean "this match has been played to a finish".
# Kept next to the model because the notification queue and the simulator both
# need to agree on what counts as finished.
FINISHED_STATUSES = ("C",)          # C = completed
UPCOMING_STATUSES = ("U",)          # U = upcoming


class Fixture(Base):
    """One scheduled Premier League match."""

    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True)

    # PulseLive's own fixture id. Unique, and the join key everything else uses:
    # team names change spelling between sources, kickoff times move, but this
    # does not.
    pl_fixture_id = Column(Integer, unique=True, index=True, nullable=False)

    season = Column(Text, index=True)
    matchweek = Column(Integer)
    home_team = Column(Text)
    away_team = Column(Text)

    # ISO 8601 UTC, e.g. '2026-09-13T14:00:00+00:00'. NULL when the Premier
    # League has not fixed the time yet. Stored as text for the same reason
    # `match_results.date` is: this project runs on SQLite locally and Postgres
    # in production, and an ISO string compares chronologically on both.
    kickoff_utc = Column(Text, index=True, nullable=True)

    # The label PulseLive renders ("Sat 13 Sep 2026, 15:00"). Kept because it is
    # what the UI shows and it carries the local-time intent; never parsed.
    kickoff_label = Column(Text, nullable=True)

    status = Column(Text, index=True)       # 'U' upcoming, 'C' completed, ...
    updated_at = Column(Text)


# Kickoff plus status is the notification queue's access path: "unplayed fixtures
# starting in the next N minutes". Without it that is a full scan every five
# minutes, on an instance that is asleep most of the time.
Index("idx_fixtures_kickoff_status", Fixture.kickoff_utc, Fixture.status)


def kickoff_from_millis(millis) -> str | None:
    """PulseLive epoch milliseconds → ISO UTC, or None if absent.

    Returns None rather than a fallback: a fixture with no published time must
    stay out of the notification queue instead of being mailed at a made-up one.
    """
    if not millis:
        return None
    try:
        return datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def upsert_fixtures(db, rows: list[dict]) -> dict:
    """Insert or update fixtures by `pl_fixture_id`.

    Upsert rather than delete-and-reinsert. The ids in `notification_log` point
    at these rows; wiping the table each refresh would either break that link or
    make "already sent" forgettable, and a forgotten send is a duplicate email.

    Returns counts, so a refresh can report what it actually changed instead of
    claiming success.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = updated = 0

    # Looked up in chunks: SQLite allows 999 bound variables by default, and a
    # single IN() over two divisions' fixtures would quietly exceed that and
    # raise mid-refresh. 380 fits today; the limit is not something to discover
    # on the day a second division is added.
    ids = [r["pl_fixture_id"] for r in rows]
    existing = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        for f in db.query(Fixture).filter(Fixture.pl_fixture_id.in_(chunk)).all():
            existing[f.pl_fixture_id] = f

    for row in rows:
        fixture = existing.get(row["pl_fixture_id"])
        if fixture is None:
            db.add(Fixture(**row, updated_at=now))
            inserted += 1
            continue
        # Only touch what changed, so `updated_at` means something: a kickoff
        # that moves is worth seeing in the log, a no-op refresh is not.
        changed = False
        for field, value in row.items():
            if getattr(fixture, field) != value:
                setattr(fixture, field, value)
                changed = True
        if changed:
            fixture.updated_at = now
            updated += 1

    db.commit()
    return {"inserted": inserted, "updated": updated, "total": len(rows)}
