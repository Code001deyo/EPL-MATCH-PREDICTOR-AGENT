"""Fetch club identity from PulseLive.

Every season is walked, not just the current one. A club relegated two years ago
still appears in `match_results`, still shows up in history and head-to-head, and
still needs its badge; fetching only the current season would leave every one of
them unidentified.

The ids do not change, so this is close to a one-off. It runs as part of the
refresh anyway because promotion happens every summer and a club arriving without
a badge is a defect nobody would think to look for.
"""

from __future__ import annotations

import requests

from db.clubs import upsert_clubs


def _fetch_season_teams(season_id: int) -> list[dict]:
    """Teams in one season, with `altIds.opta` where the feed provides it."""
    from data.ingestion import PL_API_BASE, PL_HEADERS

    url = f"{PL_API_BASE}/teams?pageSize=100&compSeasons={season_id}&altIds=true&page=0"
    response = requests.get(url, headers=PL_HEADERS, timeout=20)
    response.raise_for_status()
    return response.json().get("content", []) or []


def _row(team: dict) -> dict | None:
    short_name = (team.get("shortName") or team.get("name") or "").strip()
    if not short_name:
        return None

    club = team.get("club") or {}
    alt = team.get("altIds") or {}

    return {
        "short_name": short_name,
        "name": (team.get("name") or short_name).strip(),
        "abbr": (club.get("abbr") or "").strip() or None,
        "pl_team_id": int(team["id"]) if team.get("id") is not None else None,
        # Missing rather than guessed. A wrong Opta id renders another club's
        # badge, which is worse than no badge: it is confidently incorrect.
        "opta_id": (alt.get("opta") or "").strip() or None,
    }


def sync_clubs(seasons: int | None = None) -> dict:
    """Refresh the clubs table from every known season. Returns what changed."""
    from data.ingestion import get_season_ids
    from db.database import SessionLocal

    season_ids = get_season_ids()
    if not season_ids:
        return {"status": "no-seasons"}

    # Newest first, so the current season's spelling of a name wins when an older
    # season disagrees.
    labels = sorted(season_ids, reverse=True)
    if seasons:
        labels = labels[:seasons]

    rows: dict[str, dict] = {}
    failures = []
    for label in labels:
        try:
            for team in _fetch_season_teams(season_ids[label]):
                row = _row(team)
                if not row:
                    continue
                # First writer wins, so the newest season's data is kept — except
                # for an Opta id, which is filled in from any season that has one.
                held = rows.get(row["short_name"])
                if held is None:
                    rows[row["short_name"]] = row
                elif not held.get("opta_id") and row.get("opta_id"):
                    held["opta_id"] = row["opta_id"]
        except Exception as exc:
            # Reported, not absorbed. One season's feed failing should not stop
            # the other twelve, but it should be visible.
            failures.append(f"{label}: {type(exc).__name__}: {exc}")

    if not rows:
        return {"status": "no-clubs", "failures": failures}

    db = SessionLocal()
    try:
        counts = upsert_clubs(db, list(rows.values()))
    finally:
        db.close()

    with_badge = sum(1 for r in rows.values() if r.get("opta_id"))
    return {
        "status": "synced",
        "seasons": len(labels),
        "clubs": len(rows),
        "with_badge": with_badge,
        "without_badge": len(rows) - with_badge,
        "failures": failures,
        **counts,
    }
