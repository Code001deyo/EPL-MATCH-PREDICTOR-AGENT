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

# Official season IDs from the PulseLive API
SEASON_IDS = {
    "2019-20": 274,
    "2020-21": 363,
    "2021-22": 418,
    "2022-23": 489,
    "2023-24": 578,
    "2024-25": 719,
    "2025-26": 777,
}

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

        # Kickoff timestamp → date string DD/MM/YYYY
        kickoff_millis = f.get("kickoff", {}).get("millis")
        if kickoff_millis:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(kickoff_millis / 1000, tz=timezone.utc)
            date_str = dt.strftime("%d/%m/%Y")
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


def _is_matchweek_corrupted(db) -> bool:
    from sqlalchemy import func
    result = db.query(func.max(MatchResult.matchweek)).scalar()
    return result is not None and result > 38


def seed_database():
    init_db()
    db = SessionLocal()

    # Wipe and reseed if matchweek data is corrupted (old algorithm produced > 38)
    if _is_matchweek_corrupted(db):
        print("Corrupted matchweek data detected (max > 38). Wiping and re-seeding...")
        db.query(MatchResult).delete()
        db.commit()

    existing_seasons = {r[0] for r in db.query(MatchResult.season).distinct().all()}
    missing = [s for s in SEASON_IDS if s not in existing_seasons]

    if not missing:
        total = db.query(MatchResult).count()
        print(f"Database up to date: {total} records across {len(existing_seasons)} seasons.")
        db.close()
        return

    print(f"Seeding missing seasons: {missing}")

    all_frames = []
    for season in missing:
        season_id = SEASON_IDS[season]
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
            home_xg=None,
            away_xg=None,
            home_shots_ot=None,
            away_shots_ot=None,
            home_possession=None,
            away_possession=None,
        )
        for row in combined.itertuples()
    ]
    db.bulk_save_objects(records)
    db.commit()
    print(f"\nSeeded {len(records)} played matches into database.")

    # Validate
    from sqlalchemy import func
    for season in missing:
        max_mw = db.query(func.max(MatchResult.matchweek)).filter(
            MatchResult.season == season
        ).scalar()
        total_fx = db.query(MatchResult).filter(MatchResult.season == season).count()
        status = "✓" if max_mw and max_mw <= 38 else "✗ STILL BROKEN"
        print(f"  {season}: {total_fx} fixtures, max matchweek = {max_mw} {status}")

    db.close()


def refresh_current_season():
    """Re-fetch the current season to pick up newly played fixtures."""
    from db.database import SessionLocal, MatchResult
    CURRENT = "2025-26"
    db = SessionLocal()
    print(f"Refreshing {CURRENT}...")
    db.query(MatchResult).filter(MatchResult.season == CURRENT).delete()
    db.commit()

    season_id = SEASON_IDS[CURRENT]
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
            home_xg=None,
            away_xg=None,
            home_shots_ot=None,
            away_shots_ot=None,
            home_possession=None,
            away_possession=None,
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
