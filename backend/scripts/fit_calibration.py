"""Fit the Championship -> Premier League translation factors.

Builds the historical panel of promoted clubs: each club's final Championship
season paired with its first Premier League season, per-game. The ratio of the
two is the shrinkage factor applied to a promoted club's Championship form
until real top-flight matches accrue.

Run from backend/:  python scripts/fit_calibration.py

Reports sample size and dispersion alongside every factor. Three clubs are
promoted per season, so this panel is small by construction — the uncertainty is
part of the result, not a footnote.
"""
from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.sources import fetch_season, SeasonFileUnavailable

SEASONS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

METRICS = ["gf", "ga", "shots", "shots_ot"]


def per_game(df, club):
    """Per-game attacking and defensive rates for one club across a season."""
    home = df[df["home_team"] == club]
    away = df[df["away_team"] == club]
    games = len(home) + len(away)
    if games == 0:
        return None

    def total(col_home, col_away):
        return (home[col_home].sum(skipna=True) + away[col_away].sum(skipna=True))

    return {
        "games": games,
        "gf": total("home_goals", "away_goals") / games,
        "ga": total("away_goals", "home_goals") / games,
        "shots": total("home_shots", "away_shots") / games,
        "shots_ot": total("home_shots_ot", "away_shots_ot") / games,
    }


def clubs_in(df):
    return set(df["home_team"]) | set(df["away_team"])


def prev_season(label):
    start = int(label.split("-")[0]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def main():
    cache = {}

    def load(season, division):
        key = (season, division)
        if key not in cache:
            try:
                cache[key] = fetch_season(season, division)
            except SeasonFileUnavailable:
                cache[key] = None
        return cache[key]

    panel = []

    for season in SEASONS:
        e0 = load(season, "E0")
        prior = prev_season(season)
        e1 = load(prior, "E1")
        if e0 is None or e1 is None:
            print(f"skip {season}: source unavailable")
            continue

        promoted = clubs_in(e0) & clubs_in(e1)
        for club in sorted(promoted):
            efl = per_game(e1, club)
            epl = per_game(e0, club)
            if not efl or not epl:
                continue
            row = {"season": season, "club": club, "efl_games": efl["games"], "epl_games": epl["games"]}
            for metric in METRICS:
                if efl[metric] and efl[metric] > 0:
                    row[metric] = epl[metric] / efl[metric]
            panel.append(row)
            print(
                f"{season} {club:16} "
                + "  ".join(f"{m}:{row.get(m, float('nan')):.3f}" for m in METRICS)
            )

    print(f"\nPanel: {len(panel)} promoted club-seasons\n")
    if not panel:
        print("No panel assembled — cannot fit.")
        return

    print(f"{'metric':10} {'n':>3} {'median':>8} {'mean':>8} {'stdev':>8}  interpretation")
    for metric in METRICS:
        values = [r[metric] for r in panel if metric in r]
        if len(values) < 2:
            print(f"{metric:10} {len(values):>3}  insufficient sample")
            continue
        med = statistics.median(values)
        mean = statistics.mean(values)
        sd = statistics.stdev(values)
        direction = "lower in EPL" if med < 1 else "higher in EPL"
        print(f"{metric:10} {len(values):>3} {med:>8.3f} {mean:>8.3f} {sd:>8.3f}  {direction}")

    print(
        "\nMedian is the factor to apply (robust to the small sample); stdev is the "
        "uncertainty that must reach prediction confidence rather than be discarded."
    )


if __name__ == "__main__":
    main()
