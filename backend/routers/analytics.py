from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from routers.outcomes import result_letter as _result
from db.database import get_db, MatchResult, Prediction
from db.teams import TOP_FLIGHT, division_filter, division_name, is_played, resolve_division
import json

router = APIRouter(prefix="/analytics")

from data.ingestion import _current_season_label


def _current():
    return _current_season_label()


def _wdl(scored: int, conceded: int) -> str:
    """Win/Draw/Loss from the perspective of the team that scored `scored`."""
    if scored > conceded:
        return "W"
    return "D" if scored == conceded else "L"


@router.get("/league")
def league_analytics(
    season: str = None,
    division: str = Query(TOP_FLIGHT, description='"E0" Premier League, "E1" Championship, "all" to blend'),
    db: Session = Depends(get_db),
):
    """League table and season aggregates for ONE division.

    This endpoint had no division filter at all, and `match_results` deliberately
    holds Championship rows so promoted clubs have prior form (see promoted.py).
    The result was a 2025-26 "Premier League" table of 44 clubs in which Coventry
    ranked first on 46 games played, because its E0 and E1 matches were summed into
    one row, and a 470-match denominator under every rate on the page.

    Championship data is still reachable — deliberately, with ?division=E1 — but it
    can no longer leak into a table labelled Premier League.
    """
    division = resolve_division(division)
    # Resolved per request rather than baked into the signature, so the default
    # follows the calendar instead of whichever season was current at deploy time.
    season = season or _current()
    rows = division_filter(
        db.query(MatchResult).filter(MatchResult.season == season), division
    ).all()

    # An in-progress season holds fixtures that have not been played. They are not
    # 0-0 draws, and comparing None goals raises TypeError, so they are excluded
    # from every aggregate and reported separately.
    scheduled = sum(1 for r in rows if not is_played(r))
    rows = [r for r in rows if is_played(r)]
    if not rows:
        return {"error": "No played matches for this season and division",
                "season": season, "division": division, "scheduled": scheduled}

    total = len(rows)
    home_wins = sum(1 for r in rows if r.home_goals > r.away_goals)
    draws = sum(1 for r in rows if r.home_goals == r.away_goals)
    away_wins = sum(1 for r in rows if r.home_goals < r.away_goals)
    total_goals = sum(r.home_goals + r.away_goals for r in rows)

    # Goals per team
    team_goals = {}
    team_cs = {}
    for r in rows:
        team_goals[r.home_team] = team_goals.get(r.home_team, 0) + r.home_goals
        team_goals[r.away_team] = team_goals.get(r.away_team, 0) + r.away_goals
        if r.away_goals == 0:
            team_cs[r.home_team] = team_cs.get(r.home_team, 0) + 1
        if r.home_goals == 0:
            team_cs[r.away_team] = team_cs.get(r.away_team, 0) + 1

    top_scoring = sorted(team_goals.items(), key=lambda x: x[1], reverse=True)[:8]
    most_cs = sorted(team_cs.items(), key=lambda x: x[1], reverse=True)[:8]

    # Form table: last 5 per team
    from collections import defaultdict
    team_matches = defaultdict(list)
    for r in sorted(rows, key=lambda x: x.date):
        # W/D/L from THIS team's point of view, not H/D/A.
        # The form column used to emit the venue letters: "H" meant "this club
        # won" even for an away fixture, and "A" meant "lost". In a column headed
        # Form, next to a table of home and away records, that is close to
        # unreadable — H is naturally read as "home".
        team_matches[r.home_team].append({"pts": 3 if r.home_goals > r.away_goals else (1 if r.home_goals == r.away_goals else 0), "gf": r.home_goals, "ga": r.away_goals, "res": _wdl(r.home_goals, r.away_goals)})
        team_matches[r.away_team].append({"pts": 3 if r.away_goals > r.home_goals else (1 if r.away_goals == r.home_goals else 0), "gf": r.away_goals, "ga": r.home_goals, "res": _wdl(r.away_goals, r.home_goals)})

    form_table = []
    for team, matches in team_matches.items():
        last5 = matches[-5:]
        last10 = matches[-10:]
        form_table.append({
            "team": team,
            "played": len(matches),
            "won": sum(1 for m in matches if m["pts"] == 3),
            "drawn": sum(1 for m in matches if m["pts"] == 1),
            "lost": sum(1 for m in matches if m["pts"] == 0),
            "gf": sum(m["gf"] for m in matches),
            "ga": sum(m["ga"] for m in matches),
            "gd": sum(m["gf"] - m["ga"] for m in matches),
            "pts": sum(m["pts"] for m in matches),
            "last5_pts": sum(m["pts"] for m in last5),
            "last5": "".join(m["res"] for m in last5),
            "btts_rate": round(sum(1 for m in last10 if m["gf"] > 0 and m["ga"] > 0) / max(len(last10), 1), 2),
            "over_2_5_rate": round(sum(1 for m in last10 if m["gf"] + m["ga"] > 2) / max(len(last10), 1), 2),
        })
    form_table.sort(key=lambda x: (x["pts"], x["gd"], x["gf"]), reverse=True)

    # Goals per matchweek
    mw_goals = {}
    for r in rows:
        mw = r.matchweek
        if mw not in mw_goals:
            mw_goals[mw] = {"matchweek": mw, "home_goals": 0, "away_goals": 0, "matches": 0}
        mw_goals[mw]["home_goals"] += r.home_goals
        mw_goals[mw]["away_goals"] += r.away_goals
        mw_goals[mw]["matches"] += 1
    goals_by_mw = sorted(mw_goals.values(), key=lambda x: x["matchweek"])

    return {
        "season": season,
        # Echoed so a caller can never be unsure which league a table describes —
        # the ambiguity that let the blended table pass for a Premier League one.
        "division": division,
        "division_name": division_name(division),
        "total_matches": total,
        "scheduled_matches": scheduled,
        "avg_goals_per_game": round(total_goals / total, 2),
        "home_win_rate": round(home_wins / total, 3),
        "draw_rate": round(draws / total, 3),
        "away_win_rate": round(away_wins / total, 3),
        "top_scoring_teams": [{"team": t, "goals": g} for t, g in top_scoring],
        "most_clean_sheets": [{"team": t, "count": c} for t, c in most_cs],
        "form_table": form_table,
        "goals_by_matchweek": goals_by_mw,
    }


@router.get("/head-to-head")
def head_to_head(
    home: str = Query(...),
    away: str = Query(...),
    division: str = Query(TOP_FLIGHT, description='"E0", "E1", or "all"'),
    db: Session = Depends(get_db),
):
    """Meetings between two clubs within one division.

    Two clubs that have met in both divisions were previously reported as a single
    record, so a Premier League head-to-head silently included Championship games.
    """
    division = resolve_division(division)
    rows = division_filter(
        db.query(MatchResult).filter(
            ((MatchResult.home_team == home) & (MatchResult.away_team == away)) |
            ((MatchResult.home_team == away) & (MatchResult.away_team == home))
        ),
        division,
    ).order_by(MatchResult.date.desc()).all()
    rows = [r for r in rows if is_played(r)]

    if not rows:
        return {"total_meetings": 0, "home_wins": 0, "draws": 0, "away_wins": 0, "avg_goals": 0, "last_5": []}

    home_wins = sum(1 for r in rows if (r.home_team == home and r.home_goals > r.away_goals) or (r.away_team == home and r.away_goals > r.home_goals))
    draws = sum(1 for r in rows if r.home_goals == r.away_goals)
    away_wins = sum(1 for r in rows if (r.home_team == away and r.home_goals > r.away_goals) or (r.away_team == away and r.away_goals > r.home_goals))
    avg_goals = round(sum(r.home_goals + r.away_goals for r in rows) / len(rows), 2)

    last_5 = [
        {
            "date": r.date,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "score": f"{r.home_goals}-{r.away_goals}",
            "season": r.season,
            "matchweek": r.matchweek,
        }
        for r in rows[:5]
    ]

    return {
        "home_team": home,
        "away_team": away,
        "total_meetings": len(rows),
        "division": division,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "avg_goals": avg_goals,
        "last_5": last_5,
    }


@router.get("/team/{team}/form")
def team_form(
    team: str,
    division: str = Query(TOP_FLIGHT, description='"E0", "E1", or "all"'),
    db: Session = Depends(get_db),
):
    """Recent form for one club within one division.

    A promoted club has Championship rows stored for its feature history; without
    this filter its "last 5" mixed the two leagues, which is neither its top-flight
    form nor its Championship form.
    """
    division = resolve_division(division)
    base = db.query(MatchResult)
    home_rows = division_filter(base.filter(MatchResult.home_team == team), division).order_by(MatchResult.date.desc()).limit(20).all()
    away_rows = division_filter(db.query(MatchResult).filter(MatchResult.away_team == team), division).order_by(MatchResult.date.desc()).limit(20).all()
    home_rows = [r for r in home_rows if is_played(r)]
    away_rows = [r for r in away_rows if is_played(r)]

    matches = []
    for r in home_rows:
        matches.append({"date": r.date, "opponent": r.away_team, "venue": "H", "gf": r.home_goals, "ga": r.away_goals, "season": r.season})
    for r in away_rows:
        matches.append({"date": r.date, "opponent": r.home_team, "venue": "A", "gf": r.away_goals, "ga": r.home_goals, "season": r.season})

    matches.sort(key=lambda x: x["date"], reverse=True)
    matches = matches[:15]

    def res(m):
        if m["gf"] > m["ga"]:
            return "W"
        if m["gf"] == m["ga"]:
            return "D"
        return "L"

    last5 = matches[:5]
    last10 = matches[:10]

    return {
        "team": team,
        "division": division,
        "last_matches": [{**m, "result": res(m)} for m in matches],
        "form_string": "".join(res(m) for m in last5),
        "last5_pts": sum(3 if res(m) == "W" else (1 if res(m) == "D" else 0) for m in last5),
        "avg_gf_last5": round(sum(m["gf"] for m in last5) / max(len(last5), 1), 2),
        "avg_ga_last5": round(sum(m["ga"] for m in last5) / max(len(last5), 1), 2),
        "btts_rate": round(sum(1 for m in last10 if m["gf"] > 0 and m["ga"] > 0) / max(len(last10), 1), 2),
        "over_2_5_rate": round(sum(1 for m in last10 if m["gf"] + m["ga"] > 2) / max(len(last10), 1), 2),
        "clean_sheet_rate": round(sum(1 for m in last10 if m["ga"] == 0) / max(len(last10), 1), 2),
    }


# Model-performance reporting (live-settled vs backtested figures, kept
# separate per the P10 brief) lives in routers/analytics_model.py — split out
# to keep this file under the project's ~200-line convention. Registered
# alongside this router in main.py.
