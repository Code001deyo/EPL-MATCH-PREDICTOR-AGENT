"""The league table, built from results.

One builder, used by both the live simulation and the week-by-week
reconstruction. They had the same twenty lines each, differing only in whether a
matchweek ceiling was applied — and two copies of a points calculation is two
places for the table the simulation starts from to drift away from the table the
site displays.

Built from `match_results` directly rather than from an analytics endpoint, so a
simulation can never disagree with the standings it started from.
"""

from __future__ import annotations

from db.database import MatchResult


def build_table(db, season: str, division: str = "E0",
                up_to_matchweek: int | None = None) -> dict[str, dict]:
    """Points, goal difference and games played per club.

    `up_to_matchweek` cuts the table off after a given week, which is what the
    reconstruction needs; left None it counts everything played.

    Unplayed rows are excluded. An in-progress season holds fixtures with no
    score, and a fixture that has not happened is not a 0-0 draw — counting it as
    one would hand both clubs a point they have not earned.
    """
    query = db.query(MatchResult).filter(
        MatchResult.season == season, MatchResult.division == division
    )
    if up_to_matchweek is not None:
        query = query.filter(MatchResult.matchweek <= up_to_matchweek)

    table: dict[str, dict] = {}

    def entry(team):
        return table.setdefault(team, {
            "team": team, "points": 0, "played": 0, "scored": 0, "conceded": 0,
        })

    for row in query.all():
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
