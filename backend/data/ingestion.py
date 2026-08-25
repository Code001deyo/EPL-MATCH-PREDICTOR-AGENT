from __future__ import annotations

import pandas as pd
import numpy as np
import requests
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from db.database import SessionLocal, MatchResult, init_db

# Official Premier League PulseLive API
PL_API_BASE = "https://footballapi.pulselive.com/football"
PL_HEADERS = {
    "Origin": "https://www.premierleague.com",
    "Referer": "https://www.premierleague.com/",
    "User-Agent": "Mozilla/5.0",
}

# Premier League competition id in the PulseLive API
PL_COMPETITION_ID = 1

# Earliest season we keep and train on.
#
# This has moved twice, and both moves were measured rather than assumed.
#
# It was 2019-20, justified by a comment asserting older seasons were "not useful
# training data". That was untested, and seven seasons is thin for a 55-feature
# model.
#
# It then went to 2005-06 - the first season carrying both full match statistics
# and bookmaker odds. That was too far. Two things came out of it:
#
#   1. The extra history buys almost nothing. Walk-forward over 6,080 matches,
#      training on the most recent N seasons:
#
#          N=3   52.8%  RPS 0.2028
#          N=5   53.0%  RPS 0.2024
#          N=8   53.0%  RPS 0.2017
#          N=12  53.6%  RPS 0.2016
#          N=20  53.5%  RPS 0.2014
#
#      Past about eight seasons the curve is flat; 12 and 20 differ by 0.0002 RPS,
#      which is noise, and 12 is fractionally the better of the two on accuracy.
#
#   2. History is expensive. The feature build is quadratic in the size of the
#      stored history - every fixture's rolling windows scan the matches before
#      it - so 21 seasons made a production retrain take longer than the database
#      would hold a connection open for. It did not finish.
#
# 2014-15 gives twelve completed seasons: the flat part of the curve, at roughly a
# third of the feature-build cost of 2005-06.
EARLIEST_SEASON = "2014-15"

# 20 clubs x 38 rounds. Used to tell a completed season from a half-seeded one.
COMPLETE_SEASON_FIXTURES = 380

# Last-resort season IDs, used only when the compseasons endpoint is unreachable.
# Never add new seasons here — discovery is dynamic, see get_season_ids().
FALLBACK_SEASON_IDS = {
    "2019-20": 274,
    "2020-21": 363,
    "2021-22": 418,
    "2022-23": 489,
    "2023-24": 578,
    "2024-25": 719,
    "2025-26": 777,
}

_SEASON_ID_CACHE: dict | None = None


def _normalise_season_label(label: str) -> str | None:
    """Normalise an API season label to our canonical 'YYYY-YY' form.

    The API is inconsistent: older seasons come back as '2025/26' while the
    newest one arrives as 'English Premier League Season 2026/2027'.
    """
    import re
    m = re.search(r"(\d{4})/(\d{2,4})", label or "")
    if not m:
        return None
    start = m.group(1)
    return f"{start}-{m.group(2)[-2:]}"


def get_season_ids(force_refresh: bool = False) -> dict:
    """Discover EPL season -> compSeason id from the API.

    Season rollover (and promotion/relegation with it) needs no code change:
    a new season appears here as soon as the Premier League publishes it.
    """
    global _SEASON_ID_CACHE
    if _SEASON_ID_CACHE is not None and not force_refresh:
        return _SEASON_ID_CACHE

    url = f"{PL_API_BASE}/competitions/{PL_COMPETITION_ID}/compseasons?pageSize=100"
    try:
        resp = requests.get(url, headers=PL_HEADERS, timeout=30)
        resp.raise_for_status()
        discovered = {}
        for s in resp.json().get("content", []):
            label = _normalise_season_label(s.get("label", ""))
            if label and label >= EARLIEST_SEASON:
                discovered[label] = int(s["id"])
        if not discovered:
            raise ValueError("compseasons returned no usable seasons")
        _SEASON_ID_CACHE = dict(sorted(discovered.items()))
        print(f"Discovered {len(_SEASON_ID_CACHE)} seasons: {list(_SEASON_ID_CACHE)}")
    except Exception as e:
        print(f"Season discovery failed ({e}); falling back to pinned season ids.")
        _SEASON_ID_CACHE = dict(FALLBACK_SEASON_IDS)

    return _SEASON_ID_CACHE

# Fixture statuses: C=completed, A=active/live, U=upcoming
PLAYED_STATUSES = {"C", "A"}


def _fetch_all_fixtures(season_id: int) -> list:
    """Fetch all fixtures for a season from the PulseLive API, paginated."""
    all_fixtures = []
    page = 0
    page_size = 100
    while True:
        url = (
            f"{PL_API_BASE}/fixtures"
            f"?compSeasons={season_id}&sort=asc&pageSize={page_size}&page={page}"
        )
        try:
            resp = requests.get(url, headers=PL_HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    API error page {page}: {e}")
            break

        content = data.get("content", [])
        all_fixtures.extend(content)

        page_info = data.get("pageInfo", {})
        num_pages = int(page_info.get("numPages", 1))
        if page >= num_pages - 1:
            break
        page += 1
        time.sleep(0.2)  # be polite to the API

    return all_fixtures


def _parse_fixture(f: dict, season_label: str) -> dict | None:
    """Parse a single fixture dict from the API into a flat record."""
    try:
        teams = f.get("teams", [])
        if len(teams) != 2:
            return None

        home = teams[0]
        away = teams[1]
        status = f.get("status", "")
        gameweek = int(f["gameweek"]["gameweek"])

        # Kickoff timestamp → ISO 'YYYY-MM-DD'.
        # ISO is required, not cosmetic: rolling windows compare this column as a
        # string, and only ISO makes that comparison chronological.
        kickoff_millis = f.get("kickoff", {}).get("millis")
        if kickoff_millis:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(kickoff_millis / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = ""

        home_score = home.get("score")
        away_score = away.get("score")

        # Only store scores for completed/active matches
        if status in PLAYED_STATUSES and home_score is not None and away_score is not None:
            home_goals = int(home_score)
            away_goals = int(away_score)
        else:
            home_goals = None
            away_goals = None

        return {
            "season": season_label,
            "matchweek": gameweek,
            "date": date_str,
            "home_team": home["team"]["shortName"],
            "away_team": away["team"]["shortName"],
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": status,
            "pl_fixture_id": int(f["id"]),
        }
    except Exception:
        return None


def load_season_from_api(season_label: str, season_id: int) -> pd.DataFrame:
    raw = _fetch_all_fixtures(season_id)
    records = [_parse_fixture(f, season_label) for f in raw]
    records = [r for r in records if r is not None]
    df = pd.DataFrame(records)
    return df


# A matchweek label this high cannot come from any real English league campaign.
#
# It is NOT 38. The Premier League's own numbering legitimately runs past a
# 38-round campaign when matches are rearranged: measured against the source,
# 2006-07 and 2008-09 reach 39, 2012-13 reaches 39 and 2013-14 reaches 40 - each
# with a correct and complete 380 fixtures. A ceiling of 38 therefore condemned
# four perfectly good seasons as corrupt, which is what took production down.
#
# 60 sits above the Championship's 46 and far above any rearranged top-flight
# season, while still catching the malformed output this guard was written for.
# Completeness is not this guard's job either way - COMPLETE_SEASON_FIXTURES and
# the `partial` check below own that, and they test the thing that actually
# matters, which is whether all 380 fixtures are present.
MAX_PLAUSIBLE_MATCHWEEK = 60


def _corrupt_matchweek_seasons(db) -> list[str]:
    """Premier League seasons holding an impossible matchweek, as a list.

    Returns the offending seasons rather than a bare boolean, because the caller
    must delete *those* and nothing else.

    ## Why this no longer answers yes/no

    It used to, and the caller responded with `DELETE FROM match_results` — the
    entire table, every division, every season. That is a heuristic with a
    catastrophic action attached, and it fired in production the moment the
    history was extended back to 2005-06: one bad season took out all 22, the
    reseed then took the site down for several minutes, and because the reseed
    restored whatever tripped the guard, the next boot did it again.

    The docstring on the previous version warned about exactly this loop for the
    Championship case and fixed it by narrowing the *query*. The action stayed
    unscoped, so the same trap was one new data source away from reopening.

    Deleting only the affected seasons converges: those are re-fetched, every
    other season survives, and the site keeps answering. If a season is genuinely
    unfixable it is re-deleted each boot, which is visible in the logs and costs
    one season's ingestion rather than the whole database.

    The Championship's 46 rounds are not this guard's business, which is why the
    query stays scoped to E0 - and see MAX_PLAUSIBLE_MATCHWEEK for why the
    threshold is not 38.
    """
    from sqlalchemy import func
    rows = (
        db.query(MatchResult.season, func.max(MatchResult.matchweek))
        .filter(MatchResult.division == "E0")
        .group_by(MatchResult.season)
        .all()
    )
    return sorted(
        season for season, high in rows
        if high is not None and high > MAX_PLAUSIBLE_MATCHWEEK
    )


def _prune_seasons_before(db, earliest: str) -> int:
    """Drop stored seasons older than the configured window.

    Without this, lowering EARLIEST_SEASON is one-way: seeding only ever adds, so
    seasons pulled in under a wider setting would sit in the database forever,
    slowing every feature build while contributing nothing the model is allowed
    to train on.

    Deliberately narrow, and deliberately loud. A guard in this file previously
    answered a per-season problem with `DELETE FROM match_results` and took
    production down; this deletes exactly the seasons that fall outside the
    configured range, names them, and touches nothing else.
    """
    stale = sorted({
        season for (season,) in db.query(MatchResult.season).distinct().all()
        if season and season < earliest
    })
    if not stale:
        return 0
    print(f"Pruning {len(stale)} season(s) older than {earliest}: {stale}")
    removed = (
        db.query(MatchResult)
        .filter(MatchResult.season.in_(stale))
        .delete(synchronize_session=False)
    )
    db.commit()
    print(f"  removed {removed} rows")
    return removed


def _legacy_date_seasons(db) -> list[str]:
    """Seasons still holding a pre-P1 'DD/MM/YYYY' date.

    Those rows cannot be reinterpreted in place — a lexical sort over mixed
    formats is meaningless — so they are re-fetched. Per season, not per table,
    for the reason given in _corrupt_matchweek_seasons.

    Not scoped to a division: a legacy date is wrong wherever it appears.
    """
    rows = (
        db.query(MatchResult.season)
        .filter(MatchResult.date.like("%/%"))
        .distinct()
        .all()
    )
    return sorted(season for (season,) in rows if season)


def seed_database():
    init_db()
    db = SessionLocal()

    # Re-seed only the seasons that are actually wrong. Both guards below used to
    # delete the whole table; see _corrupt_matchweek_seasons for what that cost.
    corrupt = _corrupt_matchweek_seasons(db)
    if corrupt:
        print(
            f"Matchweek above {MAX_PLAUSIBLE_MATCHWEEK} in Premier League "
            f"season(s) {corrupt}; re-seeding those seasons only."
        )
        db.query(MatchResult).filter(
            MatchResult.season.in_(corrupt), MatchResult.division == "E0"
        ).delete(synchronize_session=False)
        db.commit()

    # P1: legacy DD/MM/YYYY rows sort by day-of-month, so every rolling window
    # built over them is wrong. Reseed rather than attempt an in-place rewrite.
    legacy = _legacy_date_seasons(db)
    if legacy:
        print(f"Legacy DD/MM/YYYY dates in season(s) {legacy}; re-seeding those seasons only.")
        db.query(MatchResult).filter(
            MatchResult.season.in_(legacy)
        ).delete(synchronize_session=False)
        db.commit()

    _prune_seasons_before(db, EARLIEST_SEASON)

    season_ids = get_season_ids()

    # A season counted as "present" if it had a single row, so a run interrupted
    # part-way left that season permanently short — it was never reconsidered.
    # Compare against the real fixture count instead. The in-progress season is
    # exempt because it is legitimately short; refresh_current_season owns it.
    from sqlalchemy import func
    counts = dict(
        db.query(MatchResult.season, func.count(MatchResult.id))
        .filter(MatchResult.division == "E0")
        .group_by(MatchResult.season)
        .all()
    )
    current = _current_season_label()

    missing, partial = [], []
    for season in season_ids:
        stored = counts.get(season, 0)
        if stored == 0:
            missing.append(season)
        elif season != current and stored < COMPLETE_SEASON_FIXTURES:
            partial.append(season)

    if partial:
        print(f"Incomplete seasons detected {[(s, counts[s]) for s in partial]}; re-fetching.")
        for season in partial:
            db.query(MatchResult).filter(
                MatchResult.season == season, MatchResult.division == "E0"
            ).delete()
        db.commit()
        missing.extend(partial)

    # Championship seasons are completed independently of the Premier League ones.
    # This runs BEFORE the up-to-date bail-out below: E0 being complete says
    # nothing about E1, and putting it after meant a fully-seeded database never
    # gained the second division at all.
    _seed_championship_seasons(db, list(season_ids))

    if not missing:
        total = db.query(MatchResult).count()
        print(f"Database up to date: {total} records across {len(counts)} seasons.")
        db.close()
        return

    print(f"Seeding seasons: {missing}")

    all_frames = []
    for season in missing:
        season_id = season_ids[season]
        print(f"Fetching {season} (id={season_id}) from Premier League API...")
        try:
            df = load_season_from_api(season, season_id)
            # Only keep played fixtures for training
            played = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
            print(f"  {len(played)} played fixtures, {len(df) - len(played)} upcoming")
            all_frames.append(played)
        except Exception as e:
            print(f"  Failed: {e}")

    if not all_frames:
        print("No data loaded.")
        db.close()
        return

    combined = pd.concat(all_frames, ignore_index=True)
    records = [
        MatchResult(
            season=row.season,
            matchweek=int(row.matchweek),
            date=str(row.date),
            home_team=row.home_team,
            away_team=row.away_team,
            home_goals=int(row.home_goals),
            away_goals=int(row.away_goals),
            division="E0",
            stats_source="pulselive",
            # Statistics stay NULL here by design: PulseLive does not publish
            # them. data/reconcile.py attaches the real values from
            # football-data.co.uk. Never fill these with a derived default.
        )
        for row in combined.itertuples()
    ]
    db.bulk_save_objects(records)
    db.commit()
    print(f"\nSeeded {len(records)} played matches into database.")

    # Validate
    for season in missing:
        max_mw = db.query(func.max(MatchResult.matchweek)).filter(
            MatchResult.season == season
        ).scalar()
        total_fx = db.query(MatchResult).filter(MatchResult.season == season).count()
        status = "OK" if max_mw and max_mw <= 38 else "STILL BROKEN"
        print(f"  {season}: {total_fx} fixtures, max matchweek = {max_mw} {status}")

    db.close()


def _current_season_label() -> str:
    """Return the current EPL season label (e.g. '2025-26') based on today's date."""
    from datetime import date
    today = date.today()
    if today.month >= 8:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        return f"{today.year - 1}-{str(today.year)[-2:]}"


def current_season_id():
    """PulseLive id for the current season, or None if it is not published yet.

    Canonical home for this lookup. It previously lived in routers/teams.py,
    which meant main.py's API health probe had no shared helper to call and
    hardcoded a season id instead.
    """
    return get_season_ids().get(_current_season_label())


def refresh_current_season():
    """Re-fetch the current season to pick up newly played fixtures."""
    from db.database import SessionLocal, MatchResult
    CURRENT = _current_season_label()
    season_ids = get_season_ids(force_refresh=True)
    season_id = season_ids.get(CURRENT)
    if season_id is None:
        # Pre-season: the new campaign may not be published yet. Skip rather
        # than crash startup — the next refresh picks it up.
        print(f"Season {CURRENT} not published by the API yet; skipping refresh.")
        return

    db = SessionLocal()
    print(f"Refreshing {CURRENT} (id={season_id})...")
    # Scoped to E0. This delete used to take the whole season, and the re-insert
    # below only writes Premier League fixtures from PulseLive — so every refresh
    # silently destroyed the current Championship season. It runs on boot and every
    # six hours, which is why the in-progress E1 rows kept disappearing minutes
    # after they were seeded.
    db.query(MatchResult).filter(
        MatchResult.season == CURRENT, MatchResult.division == "E0"
    ).delete()
    db.commit()

    df = load_season_from_api(CURRENT, season_id)
    played = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()

    records = [
        MatchResult(
            season=row.season,
            matchweek=int(row.matchweek),
            date=str(row.date),
            home_team=row.home_team,
            away_team=row.away_team,
            home_goals=int(row.home_goals),
            away_goals=int(row.away_goals),
            # These were previously omitted, so every refresh silently downgraded
            # the season's rows to division=NULL / stats_source=NULL and dropped
            # them out of coverage reporting.
            division="E0",
            stats_source="pulselive",
            # Statistics stay NULL: PulseLive does not publish them. This delete-
            # and-reinsert therefore *removes* the football-data.co.uk values that
            # reconciliation attached, which is why callers must go through
            # lifecycle.refresh_live_data() — it re-enriches straight afterwards.
        )
        for row in played.itertuples()
    ]
    db.bulk_save_objects(records)
    db.commit()
    print(f"  Refreshed: {len(records)} played fixtures in {CURRENT}")
    db.close()
    return len(records)


if __name__ == "__main__":
    seed_database()


def _seed_championship_seasons(db, season_labels: list[str]) -> None:
    """Complete the Championship alongside the Premier League.

    `promoted.py` stores a fragment of E1 — only matches involving clubs about to
    come up — which is right for seeding a promoted club's features and wrong for
    reporting a league. A season is topped up when it holds fewer than a full
    campaign; the in-progress season is exempt because it is legitimately short.
    """
    from sqlalchemy import func

    from data.championship import COMPLETE_SEASON_MATCHES, DIVISION, seed_championship

    counts = dict(
        db.query(MatchResult.season, func.count(MatchResult.id))
        .filter(MatchResult.division == DIVISION)
        .group_by(MatchResult.season)
        .all()
    )
    current = _current_season_label()
    todo = [
        s for s in season_labels
        if counts.get(s, 0) < COMPLETE_SEASON_MATCHES or s == current
    ]
    if not todo:
        return
    print(f"Completing Championship seasons: {todo}")
    try:
        seed_championship(todo, db=db)
    except Exception as exc:
        # A second-division top-up must never be the reason the app fails to boot.
        print(f"  Championship seeding failed ({type(exc).__name__}: {exc}); continuing.")
