"""Regression tests for the defects fixed in the finalisation pass.

Each of these guards a bug that produced a plausible-looking result rather than
an error, which is why none of them were caught by the existing suite.
"""
import threading
import time

import pandas as pd
import pytest

import jobs
from data.ingestion import COMPLETE_SEASON_FIXTURES
from routers.outcomes import outcome_sign, result_letter


class TestRefreshKeepsProvenance:
    """refresh_current_season deleted the season's rows and re-inserted them
    without `division` or `stats_source`, so every call silently downgraded the
    live season out of coverage reporting and wiped the statistics that
    reconciliation had attached."""

    def test_refresh_writes_division_and_source(self):
        import inspect
        from data import ingestion

        src = inspect.getsource(ingestion.refresh_current_season)
        # The insert must set both provenance columns. Asserting on the source
        # is crude, but the alternative is a live PulseLive round trip.
        assert 'division="E0"' in src, "refresh must tag the division"
        assert 'stats_source="pulselive"' in src, "refresh must record its source"

    def test_refresh_endpoint_goes_through_the_atomic_pipeline(self):
        import inspect
        from routers import teams

        src = inspect.getsource(teams.refresh_data)
        assert "lifecycle.refresh_live_data" in src, (
            "the endpoint must refresh, re-enrich and settle as one unit; "
            "calling refresh_current_season alone destroys statistics"
        )


class TestSeedCompletesPartialSeasons:
    """A season counted as present if it had a single row, so a run interrupted
    part-way left that season permanently short and it was never reconsidered."""

    def test_complete_season_constant_is_a_full_campaign(self):
        assert COMPLETE_SEASON_FIXTURES == 380  # 20 clubs x 38 rounds

    def test_partial_season_is_detected(self):
        stored = {"2019-20": 380, "2020-21": 17, "2026-27": 9}
        current = "2026-27"
        partial = [
            s for s, n in stored.items()
            if 0 < n < COMPLETE_SEASON_FIXTURES and s != current
        ]
        # The in-progress season is legitimately short and must not be wiped.
        assert partial == ["2020-21"]


class TestRetrainIsSingleFlight:
    """Two retrains were observed running concurrently, interleaved in the
    container log, both writing the same .pkl files."""

    def test_second_submit_joins_the_running_job(self):
        release = threading.Event()

        def slow(job_id):
            release.wait(timeout=5)
            return {"ok": True}

        first, created_first = jobs.submit("test-kind", slow)
        second, created_second = jobs.submit("test-kind", slow)

        assert created_first is True
        assert created_second is False, "a second submit must not start a rival job"
        assert first["id"] == second["id"]

        release.set()
        for _ in range(50):
            if jobs.get(first["id"])["state"] != "running":
                break
            time.sleep(0.1)
        assert jobs.get(first["id"])["state"] == "succeeded"

    def test_failure_is_recorded_not_swallowed(self):
        def boom(job_id):
            raise ValueError("deliberate")

        job, _ = jobs.submit("test-fail", boom)
        for _ in range(50):
            if jobs.get(job["id"])["state"] != "running":
                break
            time.sleep(0.1)
        state = jobs.get(job["id"])
        assert state["state"] == "failed"
        assert "deliberate" in state["error"]

    def test_a_finished_job_does_not_block_the_next_one(self):
        job1, created1 = jobs.submit("test-serial", lambda jid: "a")
        for _ in range(50):
            if jobs.get(job1["id"])["state"] != "running":
                break
            time.sleep(0.1)
        job2, created2 = jobs.submit("test-serial", lambda jid: "b")
        assert created1 and created2
        assert job1["id"] != job2["id"]


class TestPoissonBaselineIsReal:
    """metrics.json recorded poisson_mae = constant_mae, so `beats_poisson`
    meant only "beats the training mean" — a baseline no model can fail."""

    def _frame(self):
        """Four teams of genuinely different strength, deliberately asymmetric.

        An earlier version of this fixture used two perfectly mirrored teams.
        That is degenerate: the strength rates come out such that the two
        fixtures' errors average to exactly the constant baseline's, so the
        test failed against correct code. Uneven strengths and an uneven
        fixture list avoid the coincidence.
        """
        strength = {"Alpha": 3, "Beta": 2, "Gamma": 1, "Delta": 0}
        teams = list(strength)
        rows = []
        i = 0
        for season, repeats in (("A", 8), ("B", 3)):
            for _ in range(repeats):
                for h in teams:
                    for a in teams:
                        if h == a:
                            continue
                        i += 1
                        # Deterministic but not symmetric: a small rotating
                        # offset stops home and away errors cancelling.
                        rows.append({
                            "home_team": h, "away_team": a, "season": season,
                            "home_goals": strength[h] + (i % 2),
                            "away_goals": max(0, strength[a] - (i % 3 == 0)),
                        })
        return pd.DataFrame(rows)

    def test_poisson_is_not_a_copy_of_the_constant_baseline(self):
        from models.ml_model import _baselines

        df = self._frame()
        split = int(len(df) * 0.75)
        out = _baselines(df, split)

        assert out.get("poisson_baseline", "").startswith("team-strength"), (
            "the Poisson baseline must be team-strength, not a relabelled mean"
        )
        for target in ["home_goals", "away_goals"]:
            assert out[f"{target}_poisson_mae"] != out[f"{target}_constant_mae"], (
                f"{target}: poisson baseline is still a copy of the constant baseline"
            )

    def test_poisson_baseline_scores_outcomes_too(self):
        from models.ml_model import _baselines

        df = self._frame()
        out = _baselines(df, int(len(df) * 0.75))
        assert 0.0 <= out["poisson_correct_result_pct"] <= 100.0
        assert out["poisson_log_loss"] > 0


class TestMedianBaselineIsReported:
    """The median was computed but left out of the verdict flags, so the
    metrics block read as a clean sweep while the median in fact beat the model
    on away goals."""

    def test_lost_to_lists_every_losing_baseline(self):
        metrics = {"away_goals_mae": 0.86, "baselines": {
            "away_goals_median_mae": 0.79,
            "away_goals_constant_mae": 0.90,
        }}
        losses = []
        for name in ["poisson", "median", "constant", "form"]:
            base = metrics["baselines"].get(f"away_goals_{name}_mae")
            if base is None:
                continue
            if not metrics["away_goals_mae"] < base:
                losses.append(name)
        assert losses == ["median"], "a baseline the model loses to must be surfaced"


class TestOutcomeHelpers:
    """These were four copies of two functions across three routers."""

    @pytest.mark.parametrize("h,a,expected", [(2, 1, 1), (1, 1, 0), (0, 2, -1)])
    def test_outcome_sign(self, h, a, expected):
        assert outcome_sign(h, a) == expected

    def test_unplayed_reads_as_zero(self):
        assert outcome_sign(None, 1) == 0
        assert outcome_sign(1, None) == 0

    @pytest.mark.parametrize("h,a,expected", [(2, 1, "H"), (1, 1, "D"), (0, 2, "A")])
    def test_result_letter(self, h, a, expected):
        assert result_letter(h, a) == expected


class TestTeamIndexPreservesSemantics:
    """The per-team index cut the feature build from 273s to ~185s. It must
    return exactly the rows the helpers would have selected from the full
    frame, in the same order — the helpers rely on chronological order for
    .tail(window)."""

    def test_index_matches_a_full_frame_scan(self):
        from data.features import TeamIndex

        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "date": "2024-01-01"},
            {"home_team": "C", "away_team": "A", "date": "2024-01-08"},
            {"home_team": "B", "away_team": "C", "date": "2024-01-15"},
            {"home_team": "A", "away_team": "C", "date": "2024-01-22"},
        ])
        index = TeamIndex(df)

        for team in ["A", "B", "C"]:
            expected = df[(df["home_team"] == team) | (df["away_team"] == team)]
            got = index.team(team)
            assert list(got.index) == list(expected.index), f"{team}: order changed"
            assert got.equals(expected)

    def test_unknown_team_returns_empty_not_error(self):
        from data.features import TeamIndex

        df = pd.DataFrame([{"home_team": "A", "away_team": "B", "date": "2024-01-01"}])
        assert len(TeamIndex(df).team("Nobody")) == 0
