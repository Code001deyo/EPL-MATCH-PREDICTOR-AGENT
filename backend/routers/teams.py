from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db, MatchResult
from db.teams import top_flight_teams
import requests

router = APIRouter()

# Season membership is discovered, never pinned. The previous constants
# (2025-26 / id 777) silently froze the app to last season, so /fixtures/upcoming
# queried a completed campaign and always returned nothing.
from data.ingestion import _current_season_label, current_season_id  # noqa: F401


def current_season() -> str:
    return _current_season_label()
PL_API_BASE = "https://footballapi.pulselive.com/football"
PL_HEADERS = {
    "Origin": "https://www.premierleague.com",
    "Referer": "https://www.premierleague.com/",
    "User-Agent": "Mozilla/5.0",
}


@router.get("/teams")
def get_teams(db: Session = Depends(get_db)):
    """Selectable clubs — top flight only.

    This used to be a bare `distinct()` over `home_team` with no division filter,
    so it handed the UI 47 clubs including Championship sides that promoted.py
    stores purely as feature history. See db/teams.py.
    """
    return {"teams": top_flight_teams(db)}


@router.get("/seasons")
def get_seasons(db: Session = Depends(get_db)):
    rows = db.query(MatchResult.season).distinct().order_by(MatchResult.season).all()
    return {"seasons": [
        {"id": r[0], "label": f"{r[0]} ⏳ In Progress" if r[0] == current_season() else r[0]}
        for r in rows
    ]}


@router.get("/fixtures/recent")
def recent_fixtures(limit: int = 10, db: Session = Depends(get_db)):
    rows = db.query(MatchResult).order_by(MatchResult.date.desc()).limit(limit).all()
    return {"fixtures": [
        {
            "date": r.date, "home_team": r.home_team, "away_team": r.away_team,
            "score": f"{r.home_goals}-{r.away_goals}", "season": r.season, "matchweek": r.matchweek,
        }
        for r in rows
    ]}


@router.get("/fixtures/season/{season}")
def fixtures_by_season(season: str, db: Session = Depends(get_db)):
    """All played fixtures for a season grouped by matchweek."""
    rows = (
        db.query(MatchResult)
        .filter(MatchResult.season == season)
        .order_by(MatchResult.matchweek, MatchResult.date)
        .all()
    )
    return {
        "season": season,
        "total": len(rows),
        "fixtures": [
            {
                "id": r.id,
                "matchweek": r.matchweek,
                "date": r.date,
                "home_team": r.home_team,
                "away_team": r.away_team,
                "score": f"{r.home_goals}-{r.away_goals}",
                "label": f"MW{r.matchweek}: {r.home_team} vs {r.away_team}",
            }
            for r in rows
        ],
    }


@router.get("/fixtures/upcoming")
def upcoming_fixtures():
    """Fetch upcoming (unplayed) fixtures for the current season live from the PL API."""
    try:
        all_fixtures = []
        page, page_size = 0, 100
        while True:
            url = (
                f"{PL_API_BASE}/fixtures"
                f"?compSeasons={current_season_id()}&statuses=U&sort=asc"
                f"&pageSize={page_size}&page={page}"
            )
            resp = requests.get(url, headers=PL_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            all_fixtures.extend(content)
            page_info = data.get("pageInfo", {})
            if page >= int(page_info.get("numPages", 1)) - 1:
                break
            page += 1

        fixtures = []
        for f in all_fixtures:
            try:
                teams = f.get("teams", [])
                if len(teams) != 2:
                    continue
                gw = int(f["gameweek"]["gameweek"])
                kickoff_label = f.get("kickoff", {}).get("label", "TBC")
                fixtures.append({
                    "pl_fixture_id": int(f["id"]),
                    "matchweek": gw,
                    "kickoff": kickoff_label,
                    "home_team": teams[0]["team"]["shortName"],
                    "away_team": teams[1]["team"]["shortName"],
                    "label": f"MW{gw}: {teams[0]['team']['shortName']} vs {teams[1]['team']['shortName']}",
                    "status": f.get("status", "U"),
                })
            except Exception:
                continue

        return {"season": current_season(), "upcoming_count": len(fixtures), "fixtures": fixtures}
    except Exception as e:
        return {"error": str(e), "fixtures": []}


@router.get("/fixtures/current")
def current_season_fixtures(db: Session = Depends(get_db)):
    return fixtures_by_season(current_season(), db)


@router.post("/data/refresh")
def refresh_data():
    """Refresh the in-progress season: re-fetch, re-attach statistics, settle.

    This used to call refresh_current_season() alone. That deletes the season's
    rows and re-inserts them from PulseLive, which carries goals but no shot
    data — so every call quietly destroyed the football-data.co.uk statistics
    and reported {"status": "refreshed"} while degrading the data. The three
    steps are now one unit in lifecycle.refresh_live_data().
    """
    import lifecycle
    result = lifecycle.refresh_live_data()
    unpublished = result["played_fixtures"] is None
    return {
        # Do not claim "refreshed" when the season is not published yet: the old
        # response said refreshed with played_fixtures=null.
        "status": "season-not-published" if unpublished else "refreshed",
        "played_fixtures": result["played_fixtures"],
        "statistics_attached": result["enriched"],
        "predictions_settled": result["settled"],
        "season": result["season"],
        "last_refreshed": lifecycle.last_refreshed(),
    }


@router.get("/team/{team_name}/stats")
def team_stats(team_name: str, last_n: int = 10, db: Session = Depends(get_db)):
    home = db.query(MatchResult).filter(MatchResult.home_team == team_name).order_by(MatchResult.date.desc()).limit(last_n).all()
    away = db.query(MatchResult).filter(MatchResult.away_team == team_name).order_by(MatchResult.date.desc()).limit(last_n).all()
    home_data = [{"date": r.date, "opponent": r.away_team, "gf": r.home_goals, "ga": r.away_goals, "venue": "home"} for r in home]
    away_data = [{"date": r.date, "opponent": r.home_team, "gf": r.away_goals, "ga": r.home_goals, "venue": "away"} for r in away]
    all_matches = sorted(home_data + away_data, key=lambda x: x["date"], reverse=True)[:last_n]
    return {"team": team_name, "last_matches": all_matches}
