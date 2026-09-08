"""Reconstruct the title race week by week, so the curve is not a flat line.

A live snapshot is written after each refresh, and over a season those build the
chart on their own. But on the day this ships the chart would hold one point, and
one point is not a race — so earlier matchweeks are reconstructed: take the table
as it stood after matchweek *k*, simulate everything from *k+1* onward, record the
result.

**This is a reconstruction and is stored as one.** `kind="backfill"` in
`db/race.py`, drawn differently in the UI, captioned. It is not what the model
said at the time and must never be presented as though it were, for a specific
reason: the model has since been trained on the very matches being simulated. A
reconstruction of matchweek 3 is made by a model that has already seen matchweeks
4 onward. It answers "what does today's model think week 3 looked like", which is
a real and interesting question, and a different one from "what did we predict".

Rates are computed once for all fixtures and reused across every matchweek. That
is the expensive part — one model call per fixture — and it does not change with
the cut point, since it is the same fixed model in every case.
"""

from __future__ import annotations

from db.database import MatchResult
from db.fixtures import Fixture
from db.race import KIND_BACKFILL, save_snapshot
from models import season_sim


def _table_after(db, season: str, matchweek: int, division: str = "E0") -> dict[str, dict]:
    """The league table counting only matches up to and including `matchweek`."""
    rows = (
        db.query(MatchResult)
        .filter(MatchResult.season == season,
                MatchResult.division == division,
                MatchResult.matchweek <= matchweek)
        .all()
    )

    table: dict[str, dict] = {}

    def entry(team):
        return table.setdefault(team, {
            "team": team, "points": 0, "played": 0, "scored": 0, "conceded": 0,
        })

    for row in rows:
        if row.home_goals is None or row.away_goals is None:
            continue
        home, away = entry(row.home_team), entry(row.away_team)
        home["played"] += 1
        away["played"] += 1
        home["scored"] += row.home_goals
        home["conceded"] += row.away_goals
        away["scored"] += row.away_goals
        away["conceded"] += row.home_goals
        if row.home_goals > row.away_goals:
            home["points"] += 3
        elif row.away_goals > row.home_goals:
            away["points"] += 3
        else:
            home["points"] += 1
            away["points"] += 1

    for value in table.values():
        value["goal_difference"] = value["scored"] - value["conceded"]
    return table


def _all_fixture_rates(db, season: str, on_progress=None):
    """Model rates for every fixture of the season, played or not.

    Keyed by (home, away) so any cut point can look up the ones it still needs.
    Computed once because this is the slow part and it does not depend on the
    cut point — the model is fixed throughout a backfill.
    """
    played = {
        (r.home_team, r.away_team): r
        for r in db.query(MatchResult).filter(MatchResult.season == season).all()
    }
    upcoming = {
        (f.home_team, f.away_team): f
        for f in db.query(Fixture).filter(Fixture.season == season).all()
    }

    from models.fixture_prediction import predict_now

    rates, skipped = {}, []
    pairs = sorted(set(played) | set(upcoming))
    for i, (home, away) in enumerate(pairs):
        fixture = upcoming.get((home, away))
        when = (fixture.kickoff_utc or "")[:10] if fixture else (
            played[(home, away)].date if (home, away) in played else ""
        )
        try:
            out = predict_now(db, home, away, when)
            rates[(home, away)] = (float(out["home_lambda"]), float(out["away_lambda"]))
        except Exception as exc:
            skipped.append(f"{home} v {away}: {exc}")
        if on_progress and i % 25 == 0:
            on_progress(i, len(pairs))
    return rates, skipped


def _matchweek_of(db, season: str) -> dict[tuple, int]:
    """(home, away) → matchweek, across results and fixtures."""
    weeks = {}
    for row in db.query(MatchResult).filter(MatchResult.season == season).all():
        weeks[(row.home_team, row.away_team)] = row.matchweek
    for row in db.query(Fixture).filter(Fixture.season == season).all():
        weeks.setdefault((row.home_team, row.away_team), row.matchweek)
    return weeks


def backfill(db, season: str, simulations: int = 2_000, on_progress=None) -> dict:
    """Write a reconstructed snapshot for every completed matchweek.

    Fewer simulations than a live run by default: this produces one point per
    matchweek on a chart, where a half-point of Monte Carlo noise is invisible,
    and doing 10,000 per week would multiply the cost by the length of the season
    for no visible gain.
    """
    from sqlalchemy import func

    latest = (
        db.query(func.max(MatchResult.matchweek))
        .filter(MatchResult.season == season,
                MatchResult.division == "E0",
                MatchResult.home_goals.isnot(None))
        .scalar()
    )
    if not latest:
        return {"status": "no-results", "season": season, "matchweeks": 0}

    rates_by_pair, skipped = _all_fixture_rates(db, season, on_progress=on_progress)
    weeks = _matchweek_of(db, season)

    written = 0
    for matchweek in range(1, int(latest) + 1):
        table = _table_after(db, season, matchweek)
        if not table:
            continue

        # Everything after the cut point is "remaining", including matches that
        # have since been played — that is the whole point of a reconstruction.
        remaining = [
            (home, away, home_rate, away_rate)
            for (home, away), (home_rate, away_rate) in rates_by_pair.items()
            if weeks.get((home, away), 0) > matchweek
        ]

        teams = season_sim.simulate(table, remaining, simulations=simulations,
                                    # Fixed seed per matchweek: re-running the
                                    # backfill must not make the curve wobble by
                                    # resampling. Movement in this chart has to
                                    # mean results changed, not that dice were
                                    # rolled again.
                                    seed=1000 + matchweek)
        save_snapshot(db, season, matchweek, teams,
                      kind=KIND_BACKFILL, simulations=simulations)
        written += 1
        if on_progress:
            on_progress(matchweek, int(latest))

    return {
        "status": "ok",
        "season": season,
        "matchweeks": written,
        "simulations": simulations,
        "unpriced_fixtures": skipped,
    }
