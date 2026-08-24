"""The displayed scoreline must agree with the probabilities beside it.

This is the defect these guard. The site showed a scoreline derived by rounding
the two fitted goal rates, while the dashboard reported the accuracy of the
probability argmax. On the stored 1,140-match backtest those two answers
disagreed on 46% of matches: rounding was right 48.1% of the time, the
probabilities 53.3%. Users were shown the weaker answer and quoted the stronger
number, which is why live accuracy looked broken.
"""
import os
import sys

import numpy as np
import pytest
from scipy.stats import poisson

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.ml_model import _argmax_outcome, _poisson_probs, most_likely_scoreline

RATES = [
    (1.5, 1.2), (0.4, 0.3), (3.2, 0.5), (0.8, 2.6), (1.0, 1.0),
    (2.05, 1.95), (0.1, 0.1), (5.0, 4.9), (1.44, 1.06), (1.35, 1.15),
]


def _outcome_of(home, away):
    return 1 if home > away else (0 if home == away else -1)


@pytest.mark.parametrize("lh,la", RATES)
def test_scoreline_never_contradicts_the_probabilities(lh, la):
    """The property the whole change exists to establish."""
    home, away, outcome = most_likely_scoreline(lh, la)
    assert _outcome_of(home, away) == outcome
    assert outcome == _argmax_outcome(*_poisson_probs(lh, la))


@pytest.mark.parametrize("lh,la", RATES)
def test_it_picks_the_most_likely_cell_within_that_outcome(lh, la):
    """Not merely *a* consistent scoreline — the likeliest one."""
    home, away, outcome = most_likely_scoreline(lh, la)
    goals = np.arange(9)
    grid = np.outer(poisson.pmf(goals, lh), poisson.pmf(goals, la))
    best = max(
        ((h, a) for h in range(9) for a in range(9) if _outcome_of(h, a) == outcome),
        key=lambda ha: grid[ha],
    )
    assert (home, away) == best


def test_near_equal_rates_no_longer_force_a_draw():
    """The concrete failure, with real rates.

    1.44 and 1.06 both round to 1, so the old rule printed 1-1 — a draw — while
    the model itself gave home 45.8% against a 26.4% draw. Rounding, not the
    model, was making the call, and it made it wrongly on 18 of the 29 live
    predictions on the deployed site.
    """
    lh, la = 1.44, 1.06
    assert round(lh) == round(la)                      # the old rule said draw
    home_p, draw_p, away_p = _poisson_probs(lh, la)
    assert home_p > draw_p                             # the model did not
    _, _, outcome = most_likely_scoreline(lh, la)
    assert outcome == 1


def test_a_genuine_draw_is_still_reported_as_one():
    """The rule must not have simply abolished draws."""
    home_p, draw_p, away_p = _poisson_probs(0.35, 0.35)
    if draw_p > home_p and draw_p > away_p:
        home, away, outcome = most_likely_scoreline(0.35, 0.35)
        assert outcome == 0 and home == away


@pytest.mark.parametrize("lh,la", RATES)
def test_output_is_a_plain_int_pair(lh, la):
    """numpy integers serialise to JSON differently and reach the database as a
    different type; the API contract is plain ints."""
    home, away, _ = most_likely_scoreline(lh, la)
    assert type(home) is int and type(away) is int
    assert home >= 0 and away >= 0


def test_extreme_rates_do_not_land_outside_the_chosen_outcome():
    """At very high rates every in-mask cell can underflow. The masked argmax
    must still return a consistent cell rather than falling through to 0-0."""
    home, away, outcome = most_likely_scoreline(0.1, 7.9)
    assert _outcome_of(home, away) == outcome
