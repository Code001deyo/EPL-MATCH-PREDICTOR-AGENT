"""Keep the `fixtures` table in step with the published schedule.

`ingestion.refresh_current_season` writes only *played* matches into
`match_results`, by design. That leaves the fixtures still to come stored
nowhere: `routers/teams.upcoming_fixtures` fetches them live from PulseLive on
every request, which is fine for rendering a list and useless for anything that
has to act at a particular moment.

Two features need them on disk. A pre-match notification has to know exactly when
kickoff is and needs a stable id to record a send against; the season simulation
needs the list of matches remaining. Both read `db/fixtures.py`, and this module
is what fills it.

Runs as part of `lifecycle.refresh_live_data()` so the schedule and the results
move together — a refresh that learned a match was played but not that the next
one had been rescheduled would be half a refresh.
"""

from __future__ import annotations

from db.fixtures import kickoff_from_millis, upsert_fixtures


def _rows_from_feed(df, season_label: str) -> list[dict]:
    """Parsed PulseLive frame → `fixtures` rows.

    Rows without a usable id are dropped rather than given a synthetic one: the
    id is the only thing tying a notification to a match, and inventing one would
    let two different fixtures collide in the sent-log.
    """
    rows = []
    for row in df.itertuples():
        pl_id = getattr(row, "pl_fixture_id", None)
        if pl_id is None:
            continue
        try:
            pl_id = int(pl_id)
        except (TypeError, ValueError):
            continue

        rows.append({
            "pl_fixture_id": pl_id,
            "season": season_label,
            "matchweek": int(getattr(row, "matchweek", 0) or 0),
            "home_team": getattr(row, "home_team", None),
            "away_team": getattr(row, "away_team", None),
            # None when the Premier League has not fixed the time yet. Left as
            # None on purpose — see db/fixtures.py.
            "kickoff_utc": kickoff_from_millis(getattr(row, "kickoff_millis", None)),
            "kickoff_label": getattr(row, "kickoff_label", None),
            "status": getattr(row, "status", None),
        })
    return rows


def sync_fixtures(season_label: str | None = None) -> dict:
    """Refresh the stored schedule for one season. Returns what changed."""
    from data.ingestion import (
        _current_season_label,
        get_season_ids,
        load_season_from_api,
    )
    from db.database import SessionLocal

    season_label = season_label or _current_season_label()
    season_id = get_season_ids().get(season_label)
    if season_id is None:
        # Pre-season, exactly as in refresh_current_season: the campaign is not
        # published yet. Not an error, and not something to invent a schedule for.
        return {"status": "season-not-published", "season": season_label}

    df = load_season_from_api(season_label, season_id)
    if df is None or df.empty or "pl_fixture_id" not in df.columns:
        # A feed that returns nothing means "no news". Never read it as "the
        # season was cancelled" and clear the table — the same rule the results
        # refresh had to learn on 2026-08-29.
        return {"status": "no-fixtures-returned", "season": season_label}

    rows = _rows_from_feed(df, season_label)
    db = SessionLocal()
    try:
        counts = upsert_fixtures(db, rows)
    finally:
        db.close()

    # Worth reporting separately: a schedule where most kickoffs are unknown is
    # a schedule that will send almost no notifications, and that should be
    # visible rather than looking like nobody subscribed.
    timed = sum(1 for r in rows if r["kickoff_utc"])
    return {
        "status": "synced",
        "season": season_label,
        "kickoffs_known": timed,
        "kickoffs_unknown": len(rows) - timed,
        **counts,
    }
