"""Regression tests for the shared point-in-time indexes on the predict path.

`build_feature_vector` has always accepted `index` and `strength` so a caller can
build them once and reuse them, and the training path did. The single-prediction
path passed neither, so every request rebuilt a `MatchHistory` and a
`StrengthIndex` over the whole match frame to answer one fixture — profiled at
**90% of a prediction**, against 9% for the actual model inference, and measured
at 10-12 seconds per prediction on the deployed instance while warm.

Two things have to hold for the cache to be safe, and both are asserted here:

1. it must return the *same* indexes while the data has not moved, and rebuild
   when it has — otherwise a refresh serves predictions from stale ratings;
2. a shared index must produce a feature vector **identical** to one built from a
   freshly constructed index, or the speedup would have been bought by changing
   what the model is told.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Base, MatchResult
from db.teams import TOP_FLIGHT
from data.features import (
    build_feature_vector, invalidate_match_cache, load_matches, prediction_indexes,
)
from data.history import MatchHistory
from data.strength import StrengthIndex

TEAMS = ["Arsenal", "Chelsea", "Liverpool", "Everton", "Fulham", "Brentford"]


def _fixtures(season, start_day, rounds=6):
    """A small round-robin with varied scorelines, in true date order."""
    rows, day = [], start_day
    for r in range(rounds):
        for i in range(0, len(TEAMS), 2):
            home, away = TEAMS[i], TEAMS[(i + 1) % len(TEAMS)]
            if r % 2:
                home, away = away, home
            rows.append(MatchResult(
                season=season, matchweek=r + 1,
                date=f"2025-{start_day // 30 + 1:02d}-{day % 28 + 1:02d}",
                home_team=home, away_team=away,
                home_goals=(r + i) % 4, away_goals=(r + i + 1) % 3,
                division=TOP_FLIGHT, stats_source="test",
            ))
            day += 1
    return rows


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(_fixtures("2025-26", 1))
    session.commit()
    # The caches are module-level and shared across tests in a process, and the
    # signature of a fresh in-memory database can collide with a previous one.
    invalidate_match_cache()
    yield session
    invalidate_match_cache()
    session.close()


def test_indexes_are_reused_while_the_data_is_unchanged(db):
    first_index, first_strength = prediction_indexes(db)
    second_index, second_strength = prediction_indexes(db)
    # Identity, not equality: the point of the cache is that no second build ran.
    assert first_index is second_index
    assert first_strength is second_strength


def test_new_rows_rebuild_the_indexes(db):
    stale_index, stale_strength = prediction_indexes(db)
    db.add_all(_fixtures("2026-27", 200, rounds=1))
    db.commit()
    fresh_index, fresh_strength = prediction_indexes(db)
    # A match that has been played must be able to change a rating. Serving the
    # cached index here would quietly answer from data the season has moved past.
    assert fresh_index is not stale_index
    assert fresh_strength is not stale_strength


def test_invalidation_drops_the_indexes(db):
    before_index, before_strength = prediction_indexes(db)
    # Enrichment writes statistics onto existing rows without changing the count,
    # the max id or the max date — the signature cannot see it, which is exactly
    # why invalidate_match_cache exists and why it must clear these too.
    invalidate_match_cache()
    after_index, after_strength = prediction_indexes(db)
    assert after_index is not before_index
    assert after_strength is not before_strength


def test_shared_indexes_give_the_same_features_as_fresh_ones(db):
    """The speedup must not change a single number the model is handed."""
    frame = load_matches(db)
    cut_off = "2026-06-01"          # after every stored match, as a live fixture is
    shared_index, shared_strength = prediction_indexes(db)

    for home, away in (("Arsenal", "Chelsea"), ("Liverpool", "Everton"),
                       ("Fulham", "Brentford"), ("Chelsea", "Arsenal")):
        shared = build_feature_vector(
            frame, home, away, cut_off,
            strength=shared_strength, index=shared_index,
        )
        # What the old code did: build both from scratch, for this one fixture.
        fresh = build_feature_vector(
            frame, home, away, cut_off,
            strength=StrengthIndex(frame), index=MatchHistory(frame),
        )
        assert shared.keys() == fresh.keys()
        for key in shared:
            a, b = shared[key], fresh[key]
            both_nan = a != a and b != b          # NaN == NaN is False
            assert both_nan or a == b, f"{home} vs {away}: {key} {a!r} != {b!r}"


def test_defaulting_to_no_index_still_works(db):
    """`build_feature_vector` must keep building its own when handed neither.

    The replayed-fixture path in routers/predict.py relies on this: it cuts off
    inside the frame, so it passes None and lets the vector build an index over a
    frame with the fixture removed.
    """
    frame = load_matches(db)
    features = build_feature_vector(frame, "Arsenal", "Chelsea", "2026-06-01")
    assert features
    assert "home_elo" in features and "away_elo" in features
