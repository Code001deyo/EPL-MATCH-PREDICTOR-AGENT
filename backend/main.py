from fastapi import FastAPI, Depends, Response
import os

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db.database import init_db, get_db
from data.ingestion import get_season_ids, current_season_id, _current_season_label
import lifecycle
from routers import predict, teams, results, analytics, analytics_model, auth_router, model as model_router

# The interactive docs enumerate every route, so on a public deployment they
# advertise /auth/login, /model/retrain and /data/refresh to anyone who asks —
# which defeats keeping the operator surface unadvertised. They stay available for
# local development, where discovering the API is the point.
#
# This is not what protects those endpoints: require_admin is, and it holds
# whether or not a caller knows the path. Turning the schema off removes the
# signpost, not the lock.
_docs_enabled = os.environ.get("ENABLE_DOCS", "").lower() in ("1", "true", "yes")

app = FastAPI(
    title="EPL Score Predictor",
    version="1.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Narrowed from ["*"]. The browser reaches this API same-origin through the
# frontend's /api rewrite, so a permissive policy bought nothing and let any site
# on the internet call the API with a visitor's cookies attached.
#
# allow_credentials is required for the admin session cookie to survive a
# cross-origin request, and the CORS spec forbids pairing it with "*" — which is
# an independent reason the wildcard had to go.
_origins = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://novapl.vercel.app",
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(predict.router)
app.include_router(teams.router)
app.include_router(results.router)
app.include_router(analytics.router)
app.include_router(analytics_model.router)
app.include_router(model_router.router)


@app.on_event("startup")
def startup():
    """Return immediately; ingestion runs on a background thread.

    This hook used to run the entire pipeline inline, and uvicorn does not serve
    traffic until it returns — so a cold boot answered nothing for minutes and
    looked hung. Readiness is reported at /health/ready instead.
    """
    init_db()
    lifecycle.start()


@app.get("/health")
def health():
    """Liveness: the process is serving. Says nothing about data being loaded."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(response: Response):
    """Readiness: has startup ingestion finished, and how far did it get?

    Returns 503 while seeding so an orchestrator or the UI can distinguish
    "still loading" from "loaded and empty" — a distinction the old single
    /health endpoint could not make.
    """
    state = lifecycle.status()
    if not state["ready"]:
        response.status_code = 503
    return {
        "ready": state["ready"],
        "phase": state["phase"],
        "phases": lifecycle.PHASES,
        "started_at": state["started_at"],
        "completed_at": state["completed_at"],
        "errors": state["errors"],
    }


@app.get("/data/coverage")
def data_coverage(db: Session = Depends(get_db)):
    """Per-season data coverage and provenance.

    Lets the UI say how much of each season rests on real measurements rather
    than presenting every number with equal authority.
    """
    from sqlalchemy import func
    from db.database import MatchResult

    rows = (
        db.query(
            MatchResult.season,
            MatchResult.division,
            func.count(MatchResult.id),
            func.count(MatchResult.home_shots),
            func.max(MatchResult.date),
        )
        .group_by(MatchResult.season, MatchResult.division)
        .all()
    )

    seasons = []
    for season, division, total, with_stats, last_date in rows:
        seasons.append({
            "season": season,
            "division": division or "E0",
            "matches": total,
            "with_statistics": with_stats,
            "coverage_pct": round(with_stats / total * 100, 1) if total else 0.0,
            "last_match_date": last_date,
        })
    seasons.sort(key=lambda s: (s["season"], s["division"]))

    total_matches = sum(s["matches"] for s in seasons)
    total_stats = sum(s["with_statistics"] for s in seasons)
    return {
        "seasons": seasons,
        "total_matches": total_matches,
        "total_with_statistics": total_stats,
        "overall_coverage_pct": round(total_stats / total_matches * 100, 1) if total_matches else 0.0,
        "unavailable_statistics": ["possession", "expected_goals"],
        "sources": {
            "fixtures": "Premier League (PulseLive)",
            "statistics": "football-data.co.uk",
        },
    }


@app.get("/data/freshness")
def data_freshness(db: Session = Depends(get_db)):
    """When the data was last refreshed and what the current season is."""
    from sqlalchemy import func
    from db.database import MatchResult

    current = _current_season_label()
    latest = (
        db.query(func.max(MatchResult.date))
        .filter(MatchResult.season == current)
        .scalar()
    )
    played = db.query(MatchResult).filter(MatchResult.season == current).count()
    return {
        "current_season": current,
        "matches_played": played,
        "latest_match_date": latest,
        "last_refreshed": lifecycle.last_refreshed(),
        "seasons_known": list(get_season_ids().keys()),
    }


@app.get("/health/api")
def api_health():
    """Check if the PulseLive Premier League API is reachable and returning data."""
    import requests
    # Probe the season the app actually uses. This was hardcoded to 719 (2024-25),
    # which both violates the project's no-hardcoded-season-ids rule and meant a
    # green "live" badge proved only that a two-year-old season still resolved.
    season_id = current_season_id()
    if season_id is None:
        return {
            "status": "unresolved",
            "detail": f"No PulseLive season id for {_current_season_label()}",
            "api_url": "https://footballapi.pulselive.com/football",
        }
    url = (
        "https://footballapi.pulselive.com/football/fixtures"
        f"?compSeasons={season_id}&pageSize=1&page=0"
    )
    headers = {
        "Origin": "https://www.premierleague.com",
        "Referer": "https://www.premierleague.com/",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fixture_count = len(data.get("content", []))
        return {
            "status": "live",
            "http_status": resp.status_code,
            "fixtures_returned": fixture_count,
            "season": _current_season_label(),
            "api_url": "https://footballapi.pulselive.com/football",
        }
    except requests.exceptions.Timeout:
        return {"status": "timeout", "detail": "API did not respond within 10s"}
    except requests.exceptions.HTTPError as e:
        return {"status": "error", "http_status": resp.status_code, "detail": str(e)}
    except Exception as e:
        return {"status": "unreachable", "detail": str(e)}
