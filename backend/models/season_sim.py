"""Simulate the rest of the season, many times, and count how it ends.

The question "who wins the league?" cannot be answered by the match model on its
own: it predicts one fixture at a time, and a title depends on every remaining
result at once. So the remaining fixtures are played out repeatedly and the
outcomes are counted. A club that wins 3,200 of 10,000 simulated seasons has a
32% title probability — a frequency, not an opinion.

**What this reuses rather than reinvents.** The per-fixture goal expectations come
from the same trained model the site already serves: `ml_model.predict` returns a
Poisson rate for each side, which is exactly the parameter a simulation needs.
There is no second model here and no second set of assumptions.

**Where it samples rather than solves.** Given rates, goals are drawn from a
Poisson distribution — vectorised in numpy across all fixtures and all
simulations at once, so 380 fixtures × 10,000 seasons is one array operation
rather than 3.8 million Python iterations.

**What it does not model, said plainly.** Every fixture is drawn independently.
Real seasons are not independent: a club with nothing to play for in May is not
the club that played in March, injuries persist, and managers change. There is no
in-season model drift here either — a club's rates are those the model gives
today, held fixed across the remaining fixtures. So these are the probabilities
implied by today's model under independence, which is a narrower claim than "the
probability Arsenal win the league" and is the one the UI should make.
"""

from __future__ import annotations

import numpy as np

from db.fixtures import Fixture
from models.league_table import build_table

# 10,000 seasons puts the Monte Carlo standard error on a mid-range probability
# at about 0.5 percentage points — comfortably finer than the whole-percent the
# UI reports, so the sampling noise is not what the reader sees.
DEFAULT_SIMULATIONS = 10_000

# Above about 12 goals the Poisson tail contributes nothing that survives
# rounding, and clipping keeps one absurd draw from distorting goal difference.
MAX_GOALS = 12

TOP_FOUR = 4
RELEGATION_PLACES = 3


def current_table(db, season: str, division: str = "E0") -> dict[str, dict]:
    """The table the simulation starts from. See models/league_table.py."""
    return build_table(db, season, division)


def remaining_fixtures(db, season: str) -> list[Fixture]:
    """Matches still to be played, in kickoff order."""
    return (
        db.query(Fixture)
        .filter(Fixture.season == season, Fixture.status == "U")
        .order_by(Fixture.kickoff_utc.asc())
        .all()
    )


def fixture_rates(db, fixtures: list[Fixture], on_progress=None) -> list[tuple]:
    """(home, away, home_rate, away_rate) for each fixture the model can price.

    A fixture the model cannot build features for is skipped and reported, never
    given a default rate. Substituting an average here would silently insert a
    made-up match into every simulated season.
    """
    from models.fixture_prediction import predict_now

    rates, skipped = [], []
    for i, fixture in enumerate(fixtures):
        try:
            out = predict_now(db, fixture.home_team, fixture.away_team,
                              (fixture.kickoff_utc or "")[:10])
            rates.append((fixture.home_team, fixture.away_team,
                          float(out["home_lambda"]), float(out["away_lambda"])))
        except Exception as exc:
            skipped.append(f"{fixture.home_team} v {fixture.away_team}: {exc}")
        if on_progress and i % 20 == 0:
            on_progress(i, len(fixtures))
    return rates, skipped


def simulate(table: dict[str, dict], rates: list[tuple],
             simulations: int = DEFAULT_SIMULATIONS, seed: int | None = None) -> list[dict]:
    """Play the remaining fixtures `simulations` times and count the finishes."""
    teams = sorted(table.keys())
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)

    rng = np.random.default_rng(seed)

    points = np.tile(
        np.array([table[t]["points"] for t in teams], dtype=np.int32), (simulations, 1)
    )
    goal_diff = np.tile(
        np.array([table[t]["goal_difference"] for t in teams], dtype=np.int32), (simulations, 1)
    )
    scored = np.tile(
        np.array([table[t]["scored"] for t in teams], dtype=np.int32), (simulations, 1)
    )

    for home, away, home_rate, away_rate in rates:
        # A fixture involving a club with no rows in the table cannot be scored
        # against it. Skipping is right: inventing a row would put a club in the
        # league that the results say is not in it.
        if home not in index or away not in index:
            continue
        h, a = index[home], index[away]

        home_goals = np.clip(rng.poisson(home_rate, simulations), 0, MAX_GOALS)
        away_goals = np.clip(rng.poisson(away_rate, simulations), 0, MAX_GOALS)

        points[:, h] += np.where(home_goals > away_goals, 3, np.where(home_goals == away_goals, 1, 0))
        points[:, a] += np.where(away_goals > home_goals, 3, np.where(home_goals == away_goals, 1, 0))

        goal_diff[:, h] += home_goals - away_goals
        goal_diff[:, a] += away_goals - home_goals
        scored[:, h] += home_goals
        scored[:, a] += away_goals

    # Rank by the real Premier League order: points, then goal difference, then
    # goals scored. Encoded into one sortable key rather than sorted three times.
    # The multipliers are wide enough that a lower criterion can never overtake a
    # higher one — goal difference is bounded well inside ±1,000 over a season.
    key = points.astype(np.int64) * 10_000_000 + (goal_diff.astype(np.int64) + 1_000) * 10_000 + scored

    # argsort descending gives each simulated season's finishing order; the
    # position of each club is then read back out of it.
    order = np.argsort(-key, axis=1, kind="stable")
    positions = np.empty_like(order)
    rows = np.arange(simulations)[:, None]
    positions[rows, order] = np.arange(n)[None, :]      # 0 = champion

    results = []
    for team, i in index.items():
        place = positions[:, i]
        results.append({
            "team": team,
            "title_prob": float((place == 0).mean()),
            "top_four_prob": float((place < TOP_FOUR).mean()),
            "relegation_prob": float((place >= n - RELEGATION_PLACES).mean()),
            "projected_points": float(points[:, i].mean()),
            "points": table[team]["points"],
            "played": table[team]["played"],
            "goal_difference": table[team]["goal_difference"],
        })

    results.sort(key=lambda r: (-r["title_prob"], -r["points"], r["team"]))
    return results


def run(db, season: str, simulations: int = DEFAULT_SIMULATIONS,
        on_progress=None, seed: int | None = None) -> dict:
    """Table + rates + simulation, as one call. Used by the job and the backfill."""
    table = current_table(db, season)
    if not table:
        return {"status": "no-results", "season": season, "teams": []}

    fixtures = remaining_fixtures(db, season)
    rates, skipped = fixture_rates(db, fixtures, on_progress=on_progress)

    if on_progress:
        on_progress(len(fixtures), len(fixtures))

    teams = simulate(table, rates, simulations=simulations, seed=seed)
    played = max((t["played"] for t in teams), default=0)

    return {
        "status": "ok",
        "season": season,
        "matchweek": played,
        "simulations": simulations,
        "remaining_fixtures": len(rates),
        # Reported, never absorbed: a fixture the model could not price is a
        # match missing from every simulated season, and the caller should know.
        "unpriced_fixtures": skipped,
        "teams": teams,
    }
