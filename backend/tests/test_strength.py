"""P9 leakage and behaviour tests for the strength ratings.

The ratings are the one feature block fitted *from results*, so they are the one
place a fixture's own outcome could flow into the numbers used to predict it.
These tests assert it cannot, by mutating results and checking what moves.
"""
import pandas as pd
import numpy as np
import pytest

from data.strength import StrengthIndex, strength_features, ELO_START


def _frame(rows):
    return pd.DataFrame([
        {
            "id": i + 1, "season": "2020-21", "matchweek": 1, "date": d,
            "division": "E0", "home_team": h, "away_team": a,
            "home_goals": hg, "away_goals": ag,
        }
        for i, (d, h, a, hg, ag) in enumerate(rows)
    ])


BASE = [
    ("2020-08-01", "Arsenal", "Chelsea", 2, 0),
    ("2020-08-08", "Chelsea", "Everton", 1, 1),
    ("2020-08-15", "Everton", "Arsenal", 0, 3),
    ("2020-08-22", "Arsenal", "Everton", 1, 0),
    ("2020-08-29", "Chelsea", "Arsenal", 0, 2),
]


def test_fixture_cannot_influence_its_own_ratings():
    """The decisive test: change a match's score, and the ratings used to
    predict that match must not move."""
    original = StrengthIndex(_frame(BASE))
    before = strength_features(original, "Arsenal", "Everton", "2020-08-22")

    mutated_rows = list(BASE)
    # Turn the 2020-08-22 fixture from 1-0 into a 7-0 rout.
    mutated_rows[3] = ("2020-08-22", "Arsenal", "Everton", 7, 0)
    mutated = StrengthIndex(_frame(mutated_rows))
    after = strength_features(mutated, "Arsenal", "Everton", "2020-08-22")

    for key in before:
        b, a = before[key], after[key]
        if isinstance(b, float) and np.isnan(b):
            assert np.isnan(a), f"{key} became defined when the result changed"
        else:
            assert b == pytest.approx(a), (
                f"{key} changed when only this fixture's own result changed — leak"
            )


def test_later_results_do_not_leak_backwards():
    """A match played after the cutoff must not affect ratings at the cutoff."""
    base = StrengthIndex(_frame(BASE))
    extended = StrengthIndex(_frame(BASE + [("2020-09-05", "Arsenal", "Chelsea", 6, 0)]))

    early = strength_features(base, "Arsenal", "Chelsea", "2020-08-22")
    late = strength_features(extended, "Arsenal", "Chelsea", "2020-08-22")
    assert early["home_elo"] == pytest.approx(late["home_elo"])
    assert early["home_attack"] == pytest.approx(late["home_attack"])


def test_earlier_results_do_change_ratings():
    """Guard against the test above passing because nothing ever updates."""
    index = StrengthIndex(_frame(BASE))
    first = strength_features(index, "Arsenal", "Chelsea", "2020-08-01")
    later = strength_features(index, "Arsenal", "Chelsea", "2020-08-29")
    assert first["home_elo"] != pytest.approx(later["home_elo"])


def test_unseen_club_gets_nan_not_a_default():
    """No history means unknown. A default of 1.0 would assert 'league average'."""
    index = StrengthIndex(_frame(BASE))
    feats = strength_features(index, "Wrexham", "Arsenal", "2020-08-22")
    assert np.isnan(feats["home_attack"])
    assert np.isnan(feats["home_defence"])
    assert np.isnan(feats["home_elo"])


def test_first_appearance_sees_no_ratings():
    """A club's very first match has no prior rating to look up."""
    index = StrengthIndex(_frame(BASE))
    feats = strength_features(index, "Arsenal", "Chelsea", "2020-08-01")
    assert np.isnan(feats["home_elo"])


def test_stronger_team_earns_higher_elo():
    """Arsenal win every match in BASE; they must end rated above Chelsea."""
    index = StrengthIndex(_frame(BASE))
    after = "2020-09-30"
    assert (
        index.ratings_at("Arsenal", after)["elo"]
        > index.ratings_at("Chelsea", after)["elo"]
    )


def test_elo_is_zero_sum_across_a_match():
    """Elo transfers between clubs; it is not created."""
    index = StrengthIndex(_frame(BASE))
    after = "2020-09-30"
    total = sum(index.ratings_at(t, after)["elo"] for t in ("Arsenal", "Chelsea", "Everton"))
    assert total == pytest.approx(3 * ELO_START, abs=1e-6)


def test_championship_rows_do_not_become_top_flight_ratings():
    """E1 matches seed a promoted club's first rating but are not rated as E0."""
    rows = _frame(BASE)
    efl = pd.DataFrame([{
        "id": 99, "season": "2019-20", "matchweek": 0, "date": "2019-05-01",
        "division": "E1", "home_team": "Coventry", "away_team": "Hull",
        "home_goals": 3, "away_goals": 0,
    }])
    index = StrengthIndex(pd.concat([efl, rows], ignore_index=True))
    # Coventry never played a top-flight match, so it has no timeline entry.
    assert np.isnan(index.ratings_at("Coventry", "2020-09-30")["elo"])
