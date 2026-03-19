from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db, MatchResult
import requests

router = APIRouter()

CURRENT_SEASON = "2025-26"
CURRENT_SEASON_ID = 777
PL_API_BASE = "https://footballapi.pulselive.com/football"
PL_HEADERS = {
    "Origin": "https://www.premierleague.com",
    "Referer": "https://www.premierleague.com/",
    "User-Agent": "Mozilla/5.0",
}


@router.get("/teams")
def get_teams(db: Session = Depends(get_db)):
    rows = db.query(MatchResult.home_team).distinct().all()
    teams = sorted({r[0] for r in rows})
    return {"teams": teams}


@router.get("/seasons")
def get_seasons(db: Session = Depends(get_db)):
    rows = db.query(MatchResult.season).distinct().order_by(MatchResult.season).all()
    return {"seasons": [
        {"id": r[0], "label": f"{r[0]} ⏳ In Progress" if r[0] == CURRENT_SEASON else r[0]}
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
                f"?compSeasons={CURRENT_SEASON_ID}&statuses=U&sort=asc"
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

        return {"season": CURRENT_SEASON, "upcoming_count": len(fixtures), "fixtures": fixtures}
    except Exception as e:
        return {"error": str(e), "fixtures": []}


@router.get("/fixtures/current")
def current_season_fixtures(db: Session = Depends(get_db)):
    return fixtures_by_season(CURRENT_SEASON, db)


@router.post("/data/refresh")
def refresh_data():
    """Re-fetch the current season from the PL API to pick up newly played fixtures."""
    from data.ingestion import refresh_current_season
    count = refresh_current_season()
    return {"status": "refreshed", "played_fixtures": count, "season": CURRENT_SEASON}


@router.get("/team/{team_name}/stats")
def team_stats(team_name: str, last_n: int = 10, db: Session = Depends(get_db)):
    home = db.query(MatchResult).filter(MatchResult.home_team == team_name).order_by(MatchResult.date.desc()).limit(last_n).all()
    away = db.query(MatchResult).filter(MatchResult.away_team == team_name).order_by(MatchResult.date.desc()).limit(last_n).all()
    home_data = [{"date": r.date, "opponent": r.away_team, "gf": r.home_goals, "ga": r.away_goals, "venue": "home"} for r in home]
    away_data = [{"date": r.date, "opponent": r.home_team, "gf": r.away_goals, "ga": r.home_goals, "venue": "away"} for r in away]
    all_matches = sorted(home_data + away_data, key=lambda x: x["date"], reverse=True)[:last_n]
    return {"team": team_name, "last_matches": all_matches}
