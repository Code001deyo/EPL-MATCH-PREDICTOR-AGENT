"""Bookmaker odds as model features.

## Why odds are the strongest feature available

A closing price is not one forecaster's opinion. It is the settled position of
every professional syndicate, insider and model that bet into that market, and it
prices things this codebase has no access to at all - a manager resting six
players for a cup tie, a fitness doubt resolved at breakfast, a dressing-room
story that never reaches a statistics feed.

Measured on 7,980 Premier League matches (2005-06 to 2025-26): picking the
favourite implied by Bet365's closing price is right **54.8%** of the time, and
Pinnacle's **55.2%**, against **45.6%** for always choosing the home side. That is
very close to the ceiling for this problem - the published state of the art spans
roughly 48% to 56%, and the 2023 Soccer Prediction Challenge was won by a model
that did nothing but average bookmakers.

## Why implied probability rather than the raw price

Decimal odds are a reciprocal scale: the gap between 1.10 and 1.20 is enormous in
probability terms, and the gap between 15.0 and 20.0 is negligible. Handing a
tree the raw number makes it discover 1/x from split points. `1/odds` is that
transform, done once and exactly.

## Why the vig has to come out

Bookmakers publish prices whose implied probabilities sum to more than 1 - that
excess is the margin. Left in, every probability is inflated by a factor that
varies by bookmaker and by market, so the same true chance reads differently
across seasons as competition changed the typical margin. Normalising by the
overround removes it.

The overround itself is kept as a feature: a wide margin signals a market the
bookmaker is unsure about or one with thin liquidity, and that uncertainty is
information about the fixture.

## Leakage

There is none, and it is worth stating plainly because it looks like there might
be. These are *pre-match* prices, fixed before kick-off. Nothing about the result
is in them. They are exactly as available at prediction time as a team's league
position - provided the live path actually fetches them, which is what
`upcoming_odds()` is for.
"""
from __future__ import annotations

import io
import threading
import time

import numpy as np

ODDS_FEATURES = [
    "odds_implied_home",
    "odds_implied_draw",
    "odds_implied_away",
    "odds_overround",
]

# A price outside this range is a parsing artefact rather than a market.
# Real 1X2 prices sit roughly in [1.01, 1000].
MIN_ODD = 1.01
MAX_ODD = 1000.0


def _valid(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or not (MIN_ODD <= number <= MAX_ODD):
        return None
    return number


def implied_probabilities(home_odds, draw_odds, away_odds):
    """De-vigged (home, draw, away) probabilities and the overround.

    Returns four NaNs if any leg is missing or unusable. Partial odds are not
    salvaged: two of the three prices cannot be normalised without inventing the
    third, and an invented probability is indistinguishable downstream from a
    real one.
    """
    legs = [_valid(home_odds), _valid(draw_odds), _valid(away_odds)]
    if any(leg is None for leg in legs):
        return np.nan, np.nan, np.nan, np.nan

    raw = np.array([1.0 / leg for leg in legs])
    overround = float(raw.sum())
    if overround <= 0:
        return np.nan, np.nan, np.nan, np.nan

    devigged = raw / overround
    return float(devigged[0]), float(devigged[1]), float(devigged[2]), overround


def odds_feature_dict(home_odds, draw_odds, away_odds) -> dict:
    """The four odds features, keyed as FEATURE_COLS expects.

    Missing odds produce NaN rather than a neutral 1/3. Both model backends split
    on NaN natively, so the model can learn "no market price was available" as its
    own condition - which is a real and informative state, unlike a fabricated
    even-money prior that is indistinguishable from a genuinely balanced fixture.
    """
    home_p, draw_p, away_p, overround = implied_probabilities(home_odds, draw_odds, away_odds)
    return {
        "odds_implied_home": home_p,
        "odds_implied_draw": draw_p,
        "odds_implied_away": away_p,
        "odds_overround": overround,
    }


def market_pick(home_odds, draw_odds, away_odds):
    """The market's own favourite, as 1 / 0 / -1, or None without a full price.

    Used to print the bookmaker's accuracy beside the model's on the same
    fixtures. A model's number means very little without the market's next to it.
    """
    home_p, draw_p, away_p, _ = implied_probabilities(home_odds, draw_odds, away_odds)
    if np.isnan(home_p):
        return None
    best = max(home_p, draw_p, away_p)
    if best == home_p:
        return 1
    return 0 if best == draw_p else -1


# ------------------------------------------------------------------ live odds

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
_CACHE_TTL_SECONDS = 1800
_cache = {"fetched_at": 0.0, "rows": {}}
_cache_lock = threading.Lock()

# Preference order. Pinnacle is the sharpest of these and Bet365 the most
# consistently present; the market average is the most robust when a single book
# is missing a line. First complete triple wins.
_PRICE_SETS = [
    ("PSH", "PSD", "PSA"),
    ("B365H", "B365D", "B365A"),
    ("AvgH", "AvgD", "AvgA"),
]


def _fetch_fixture_odds() -> dict:
    """Pre-match prices for upcoming fixtures, keyed (home, away).

    Deliberately failure-tolerant. If this source is unreachable the prediction
    still has to work - it simply proceeds with the odds features absent, which is
    the same state as a fixture with no published line.
    """
    import pandas as pd
    import requests

    from .sources.aliases import canonical_team

    resp = requests.get(FIXTURES_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    frame = pd.read_csv(io.StringIO(resp.content.decode("utf-8-sig", errors="replace")))

    rows = {}
    for row in frame.to_dict("records"):
        if row.get("Div") not in ("E0", "E1"):
            continue
        try:
            home = canonical_team(str(row.get("HomeTeam", "")), strict=False)
            away = canonical_team(str(row.get("AwayTeam", "")), strict=False)
        except Exception:
            continue
        for home_col, draw_col, away_col in _PRICE_SETS:
            triple = (row.get(home_col), row.get(draw_col), row.get(away_col))
            if all(_valid(value) is not None for value in triple):
                rows[(home, away)] = triple
                break
    return rows


def upcoming_odds(home_team: str, away_team: str):
    """Pre-match odds for a fixture that has not been played, or None.

    Cached for 30 minutes. Without this the odds features would be populated for
    every historical match and empty for every live prediction - so the model
    would lean on a feature at training time that is missing exactly when it is
    asked to do its job. That failure is silent and severe, which is why the live
    path fetches rather than shrugging.
    """
    global _cache
    with _cache_lock:
        stale = (time.time() - _cache["fetched_at"]) > _CACHE_TTL_SECONDS
        if stale:
            try:
                _cache = {"fetched_at": time.time(), "rows": _fetch_fixture_odds()}
            except Exception as exc:
                print(f"[odds] upcoming fixtures unavailable: {type(exc).__name__}: {exc}")
                # Timestamp the failure too, so an outage is not retried on every
                # single prediction while the source is down.
                _cache = {"fetched_at": time.time(), "rows": _cache.get("rows", {})}
        return _cache["rows"].get((home_team, away_team))
