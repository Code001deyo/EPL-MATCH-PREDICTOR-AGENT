"""P2-P6 regression tests.

These guard the defect class that motivated the rebuild: a fabricated number
presented to the model as if it were a measurement.
"""
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.sources.aliases import canonical_team, UnknownClubError
from data.sources.football_data import season_code, _to_iso
from data.calibration import (
    CALIBRATION_FACTORS, prior_weight, translate, relative_uncertainty,
)
from data.features import _team_rolling, ROLLING_FEATURES, _ratio


def _list_from_model_module(name: str) -> list:
    """Read a module-level list from ml_model.py without importing xgboost.

    The heavy ML dependency is only present in the container; these assertions
    are about the declared feature contract, so parse rather than import.
    """
    import ast
    path = os.path.join(os.path.dirname(__file__), "..", "models", "ml_model.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in ml_model.py")


FEATURE_COLS = _list_from_model_module("FEATURE_COLS")
STAT_TARGETS = _list_from_model_module("STAT_TARGETS")


# ---------------------------------------------------------------- P2: sources

def test_club_aliases_resolve_across_sources():
    assert canonical_team("Man United") == "Man Utd"
    assert canonical_team("Tottenham") == "Spurs"
    # Already canonical names pass through untouched.
    assert canonical_team("Arsenal") == "Arsenal"
    assert canonical_team("Nott'm Forest") == "Nott'm Forest"


def test_unknown_club_raises_rather_than_inventing_a_team():
    """A silently accepted unknown name creates a phantom club with no history."""
    with pytest.raises(UnknownClubError):
        canonical_team("Not A Real Club FC", strict=True)


def test_season_code_maps_to_source_path():
    assert season_code("2025-26") == "2526"
    assert season_code("2019-20") == "1920"


def test_source_dates_convert_to_iso():
    assert _to_iso("15/08/2025") == "2025-08-15"
    assert _to_iso("05/01/2026") == "2026-01-05"
    assert _to_iso("") is None


# ------------------------------------------------------------ P4: calibration

def test_calibration_factors_carry_sample_size_and_spread():
    for metric, (factor, stdev, n) in CALIBRATION_FACTORS.items():
        assert factor > 0, metric
        assert stdev >= 0, metric
        assert n >= 10, f"{metric} fitted on too small a panel to report"


def test_promoted_scoring_is_shrunk_and_conceding_inflated():
    """The fitted direction: promoted clubs score less and concede more."""
    assert translate("gf", 2.0) < 2.0
    assert translate("ga", 1.0) > 1.0


def test_prior_weight_decays_to_zero_with_real_matches():
    assert prior_weight(0) == 1.0
    assert prior_weight(10) == 0.0
    assert prior_weight(20) == 0.0
    assert 0 < prior_weight(5) < 1
    # Monotonic: more evidence never increases reliance on the prior.
    weights = [prior_weight(m) for m in range(0, 12)]
    assert all(a >= b for a, b in zip(weights, weights[1:]))


def test_defensive_translation_is_the_least_certain():
    """Goals-against has stdev 1.002 on factor 2.044 — that must be visible."""
    assert relative_uncertainty("ga") > relative_uncertainty("gf")


# --------------------------------------------------------- P5: no fabrication

def test_unknown_team_yields_nan_not_zero():
    empty = pd.DataFrame(columns=[
        "date", "home_team", "away_team", "home_goals", "away_goals",
        "home_shots", "away_shots", "home_shots_ot", "away_shots_ot",
        "home_corners", "away_corners", "home_fouls", "away_fouls",
        "home_yellow_cards", "away_yellow_cards",
    ])
    stats = _team_rolling(empty, "Coventry", "2026-08-30")
    for feature in ROLLING_FEATURES:
        value = stats[feature]
        assert value is None or (isinstance(value, float) and math.isnan(value)), (
            f"{feature} came back as {value!r}; unknown must be NaN, never a number"
        )
    assert stats["matches_played"] == 0


def test_no_synthetic_constants_remain_in_feature_layer():
    """The specific fabrications that made two thirds of the vector fake."""
    # Every file the feature layer is spread across, not just features.py: the
    # per-fixture computation moved to vector.py and the windowing to history.py,
    # and a guard that only reads one of the three would pass while a fabricated
    # constant sat in another.
    layer = os.path.join(os.path.dirname(__file__), "..", "data")
    for name in ["features.py", "vector.py", "history.py"]:
        source = open(os.path.join(layer, name), encoding="utf-8").read()
        for literal in ["* 4.5", "* 2.5", "fallback=50.0", "fallback=11.0", "fallback=1.5"]:
            assert literal not in source, f"synthetic fallback {literal!r} is back in {name}"


def test_ratio_propagates_missingness():
    assert math.isnan(_ratio(np.nan, 2.0))
    assert math.isnan(_ratio(1.0, 0))
    assert _ratio(1.0, 2.0) == 0.5


def test_possession_and_xg_are_not_modelled():
    """Neither source publishes them, so neither may appear as a feature."""
    for col in FEATURE_COLS:
        assert "poss" not in col, f"possession feature {col} is unavailable from any source"
        assert "xg" not in col.lower(), f"{col} implies expected goals, which is not measured"
    for target in STAT_TARGETS:
        assert "possession" not in target


def test_sufficiency_features_are_present():
    """The model must be able to tell thin evidence from thick."""
    for required in [
        "home_top_flight_matches", "away_top_flight_matches",
        "home_is_newly_promoted", "away_is_newly_promoted",
    ]:
        assert required in FEATURE_COLS
