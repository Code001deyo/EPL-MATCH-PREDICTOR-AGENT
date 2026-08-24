"""Cross-division calibration — translating Championship form to Premier League.

A promoted club's Championship record is real evidence, but it is not Premier
League evidence. Feeding it in untranslated replaces one bias (all-zero features)
with another (overrating promoted sides).

Factors below were fitted on the historical panel of promoted clubs — each club's
final Championship season paired with its first Premier League season, per game.
Refit with:  python scripts/fit_calibration.py

Fitted 2026-08-23 on 21 promoted club-seasons (2019-20 through 2025-26).
"""
from __future__ import annotations

# metric -> (factor, stdev, sample size)
# Factor is the median ratio of Premier League per-game output to Championship
# per-game output. Median rather than mean: the panel is small and contains real
# outliers (Burnley 2025-26 conceded at 5.7x its Championship rate).
CALIBRATION_FACTORS = {
    "gf":       (0.605, 0.190, 21),
    "ga":       (2.044, 1.002, 21),
    "shots":    (0.761, 0.106, 21),
    "shots_ot": (0.718, 0.133, 21),
}

# Matches after which Championship history carries no weight at all. Real
# observed top-flight form progressively replaces the translated estimate.
FULL_WEIGHT_AT = 0
ZERO_WEIGHT_AT = 10


def prior_weight(matches_played: int) -> float:
    """Weight given to translated Championship form, decaying with real matches.

    1.0 with no Premier League matches played, reaching 0.0 at ZERO_WEIGHT_AT.
    """
    if matches_played <= FULL_WEIGHT_AT:
        return 1.0
    if matches_played >= ZERO_WEIGHT_AT:
        return 0.0
    span = ZERO_WEIGHT_AT - FULL_WEIGHT_AT
    return 1.0 - (matches_played - FULL_WEIGHT_AT) / span


def translate(metric: str, value: float) -> float:
    """Apply the fitted division factor to a Championship per-game value."""
    if value is None:
        return None
    entry = CALIBRATION_FACTORS.get(metric)
    if entry is None:
        return value
    factor, _stdev, _n = entry
    return value * factor


def relative_uncertainty(metric: str) -> float:
    """Dispersion of the fitted factor, as a fraction of the factor itself.

    Feeds prediction confidence: goals-against translates with a stdev of 1.002
    on a factor of 2.044, so a promoted club's defensive estimate is far less
    trustworthy than its attacking one. Discarding that would present a rough
    estimate with the same authority as observed history.
    """
    entry = CALIBRATION_FACTORS.get(metric)
    if entry is None:
        return 0.0
    factor, stdev, _n = entry
    return stdev / factor if factor else 0.0


def blend(observed: float | None, translated: float | None, matches_played: int) -> float | None:
    """Combine observed Premier League form with translated Championship form."""
    weight = prior_weight(matches_played)
    if translated is None:
        return observed
    if observed is None:
        return translated if weight > 0 else None
    return weight * translated + (1.0 - weight) * observed


def calibration_confidence_penalty(matches_played: int, is_promoted: bool) -> float:
    """How much to discount confidence for a prediction resting on priors.

    Returns 0.0 for a club with a full Premier League record, rising toward the
    calibration's own relative uncertainty when nothing has been observed yet.
    """
    if not is_promoted:
        return 0.0
    weight = prior_weight(matches_played)
    worst = max(relative_uncertainty(m) for m in CALIBRATION_FACTORS)
    return weight * worst
