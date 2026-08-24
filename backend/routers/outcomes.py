"""Match-outcome helpers shared by the routers.

`_result` was defined identically in routers/analytics.py and
routers/analytics_model.py, and `_outcome_sign` identically in
routers/analytics_model.py and routers/model.py. Four copies of two four-line
functions is four places for the definition of "a draw" to drift apart.
"""


def result_letter(home_goals, away_goals) -> str:
    """H / D / A, for league tables and form strings."""
    if home_goals > away_goals:
        return "H"
    if home_goals == away_goals:
        return "D"
    return "A"


def outcome_sign(home_goals, away_goals) -> int:
    """1 home win, 0 draw, -1 away win. Unplayed fixtures read as 0.

    The 0-for-unknown collapse is why callers must filter unsettled rows before
    scoring accuracy rather than relying on this to flag them.
    """
    if home_goals is None or away_goals is None:
        return 0
    if home_goals > away_goals:
        return 1
    return 0 if home_goals == away_goals else -1
