"""Team strength ratings — attack, defence and Elo.

## Why this exists

Every feature in `features.py` is a club's own rolling average, unadjusted for
who it played. Two clubs averaging 1.8 goals per game look identical to the model
even if one faced the top six and the other faced the bottom six. Strength of
schedule is invisible, so the model has no representation of *team strength* at
all — which is why it separated so weakly from a constant baseline (44.7% correct
results against 43.4% for always-predict-home).

This module supplies that representation:

- **Attack / defence**, a multiplicative Poisson strength model in the
  Dixon-Coles tradition. `expected_home = league_home_rate * attack[home] *
  defence[away]`. Both sides' ratings and the fixture's own expected goal rates
  become features, which hands the booster a structurally informed prior instead
  of asking it to rediscover league structure from rolling means.
- **Elo**, a single scalar per club. Cheap, well understood, and a useful control:
  if Elo alone matches the full feature set, the feature set has a problem.

## Leakage

This is the highest-risk part of the phase. Ratings fitted over a whole season
encode the result of the match being predicted. So ratings here are **online**:
one forward pass in date order, and a club's rating is only ever updated *after*
a match is scored. `ratings_at(team, date)` returns the last rating that took
effect strictly before `date`. A fixture can therefore never influence the
numbers used to predict it — by construction, not by convention.

`tests/test_strength.py` asserts this against mutated results.
"""
from __future__ import annotations

import bisect
import math
from collections import defaultdict

import numpy as np

from .calibration import translate

# Elo. K is deliberately modest: league strength moves slowly and a high K makes
# the rating chase single results, which is what the rolling-form features
# already do.
ELO_START = 1500.0
ELO_K = 20.0
ELO_HOME_ADVANTAGE = 60.0

# A club promoted from the Championship starts below the league mean rather than
# at it. 1420 is roughly one home advantage plus a little below par — the level
# a newly promoted side is actually rated at, not the average of a division it
# has never played in. Seeding at ELO_START would claim a promoted club is an
# average Premier League team on day one, which is a fabricated prior.
ELO_PROMOTED_START = 1420.0

# Poisson strength model. Ratings live in log space and are updated by gradient
# ascent on the Poisson log-likelihood, whose derivative w.r.t. a log-rating is
# simply (observed - expected).
STRENGTH_LR = 0.02
STRENGTH_CLAMP = 0.9          # |log rating| ceiling, ~2.5x either way
STRENGTH_REGRESSION = 0.995   # per-match pull back toward league average

# Long-run Premier League scoring rates, used as the starting reference for the
# multiplicative ratings and then updated online as matches are scored.
#
# These are constants rather than the mean of the loaded frame for a reason that
# a test caught: taking the mean over the whole DataFrame makes every historical
# rating depend on matches that had not been played yet. Appending a single
# future 6-0 moved the league mean, which moved the seeds, which moved every
# rating in the past. That is backwards-flowing leakage, and it is invisible
# because the numbers still look entirely reasonable.
LEAGUE_HOME_RATE = 1.50
LEAGUE_AWAY_RATE = 1.20
RATE_LR = 0.002               # online update toward the observed league rate


class StrengthIndex:
    """Forward-pass ratings with point-in-time lookup.

    Built once over the full match history. Per team it holds a timeline of
    (effective_date, attack, defence, elo, matches) entries, so a lookup is a
    bisect rather than a refit.
    """

    def __init__(self, df, division: str = "E0"):
        self._timeline = defaultdict(list)   # team -> list of (date, dict)
        self._dates = defaultdict(list)      # team -> list of date (bisect key)
        self._rate_dates: list = []
        self._rates: list = []
        self.league_home_rate = LEAGUE_HOME_RATE
        self.league_away_rate = LEAGUE_AWAY_RATE
        if df is not None and len(df):
            self._build(df, division)

    # ---------------------------------------------------------------- build

    def _build(self, df, division: str) -> None:
        if "division" in df.columns:
            top = df[df["division"].fillna("E0") == division]
        else:
            top = df

        log_att: dict = {}
        log_def: dict = {}
        elo: dict = {}
        played: dict = defaultdict(int)

        # Seeded from documented constants and updated online, so no rating ever
        # depends on a match that had not been played at the time.
        home_rate = LEAGUE_HOME_RATE
        away_rate = LEAGUE_AWAY_RATE

        # Championship form, used only to seed a club's first top-flight rating.
        efl = self._efl_rates(df, division)

        for row in top.itertuples(index=False):
            h, a = row.home_team, row.away_team
            date = row.date

            for team in (h, a):
                if team not in log_att:
                    log_att[team], log_def[team] = self._seed(team, efl, home_rate, away_rate)
                    elo[team] = ELO_PROMOTED_START if team in efl else ELO_START

            hg, ag = row.home_goals, row.away_goals
            if hg is None or ag is None:
                continue
            try:
                hg, ag = float(hg), float(ag)
            except (TypeError, ValueError):
                continue
            if math.isnan(hg) or math.isnan(ag):
                continue

            exp_h = home_rate * math.exp(log_att[h]) * math.exp(log_def[a])
            exp_a = away_rate * math.exp(log_att[a]) * math.exp(log_def[h])

            # Poisson score function. Scaled by the expected rate so a 1-goal
            # surprise in a low-scoring fixture moves the rating more than the
            # same surprise in a high-scoring one.
            log_att[h] = _step(log_att[h], (hg - exp_h) / max(exp_h, 0.3))
            log_def[a] = _step(log_def[a], (hg - exp_h) / max(exp_h, 0.3))
            log_att[a] = _step(log_att[a], (ag - exp_a) / max(exp_a, 0.3))
            log_def[h] = _step(log_def[h], (ag - exp_a) / max(exp_a, 0.3))

            _update_elo(elo, h, a, hg, ag)
            played[h] += 1
            played[a] += 1

            home_rate += RATE_LR * (hg - home_rate)
            away_rate += RATE_LR * (ag - away_rate)
            self._rate_dates.append(date)
            self._rates.append((home_rate, away_rate))

            # Record the state *after* this match, stamped with its date. A
            # lookup for a later fixture takes the last entry stamped strictly
            # earlier, so it sees every result up to but not including its own —
            # and two fixtures on the same day cannot see each other.
            self._append(h, date, log_att, log_def, elo, played)
            self._append(a, date, log_att, log_def, elo, played)

        self.league_home_rate = home_rate
        self.league_away_rate = away_rate

    def _seed(self, team, efl: dict, home_rate: float, away_rate: float):
        """Initial attack/defence for a club's first top-flight match.

        A club with real Championship history is seeded from it, translated to
        Premier League scale through the P4 calibration factors. A club with no
        history at all is seeded at league average (log 0) — the only defensible
        starting point when nothing is known, and it carries no information, so
        the model's sufficiency features are what flag it as thin evidence.
        """
        rates = efl.get(team)
        if not rates:
            return 0.0, 0.0
        gf, ga = rates
        att = _clamp(math.log(max(translate("gf", gf), 0.2) / max(home_rate, 0.2)))
        dfc = _clamp(math.log(max(translate("ga", ga), 0.2) / max(away_rate, 0.2)))
        return att, dfc

    @staticmethod
    def _efl_rates(df, division: str) -> dict:
        """Per-club goals for/against in the non-top-flight rows we hold."""
        if "division" not in df.columns:
            return {}
        lower = df[df["division"].fillna("E0") != division]
        if lower.empty:
            return {}
        acc = defaultdict(lambda: [0.0, 0.0, 0])
        for row in lower.itertuples(index=False):
            if row.home_goals is None or row.away_goals is None:
                continue
            acc[row.home_team][0] += row.home_goals
            acc[row.home_team][1] += row.away_goals
            acc[row.home_team][2] += 1
            acc[row.away_team][0] += row.away_goals
            acc[row.away_team][1] += row.home_goals
            acc[row.away_team][2] += 1
        return {t: (gf / n, ga / n) for t, (gf, ga, n) in acc.items() if n > 0}

    def _append(self, team, date, log_att, log_def, elo, played) -> None:
        self._dates[team].append(date)
        self._timeline[team].append({
            "attack": math.exp(log_att[team]),
            "defence": math.exp(log_def[team]),
            "elo": elo[team],
            "matches": played[team],
        })

    # --------------------------------------------------------------- lookup

    def ratings_at(self, team: str, before_date: str) -> dict:
        """Ratings in force strictly before `before_date`.

        A club with no prior top-flight match returns NaN ratings — not a default
        of 1.0, which would assert it is exactly league average.
        """
        dates = self._dates.get(team)
        if not dates:
            return _unknown()
        idx = bisect.bisect_left(dates, before_date)
        if idx == 0:
            return _unknown()
        return dict(self._timeline[team][idx - 1])

    def rates_at(self, before_date: str):
        """League home/away scoring rates as of `before_date`."""
        idx = bisect.bisect_left(self._rate_dates, before_date)
        if idx == 0:
            return LEAGUE_HOME_RATE, LEAGUE_AWAY_RATE
        return self._rates[idx - 1]

    def expected_goals(self, home_team: str, away_team: str, before_date: str):
        """The strength model's own rate prediction for this fixture."""
        h = self.ratings_at(home_team, before_date)
        a = self.ratings_at(away_team, before_date)
        home_rate, away_rate = self.rates_at(before_date)
        exp_h = home_rate * h["attack"] * a["defence"]
        exp_a = away_rate * a["attack"] * h["defence"]
        return exp_h, exp_a


def _unknown() -> dict:
    return {"attack": np.nan, "defence": np.nan, "elo": np.nan, "matches": 0}


def _clamp(value: float) -> float:
    return max(-STRENGTH_CLAMP, min(STRENGTH_CLAMP, value))


def _step(current: float, gradient: float) -> float:
    return _clamp(current * STRENGTH_REGRESSION + STRENGTH_LR * gradient)


def _update_elo(elo: dict, home: str, away: str, hg: float, ag: float) -> None:
    diff = (elo[home] + ELO_HOME_ADVANTAGE) - elo[away]
    expected_home = 1.0 / (1.0 + 10 ** (-diff / 400.0))
    actual_home = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
    # Margin of victory multiplier: a 4-0 is more evidence than a 1-0, damped so
    # a single rout cannot dominate the rating.
    margin = 1.0 + math.log1p(abs(hg - ag))
    change = ELO_K * margin * (actual_home - expected_home)
    elo[home] += change
    elo[away] -= change


STRENGTH_FEATURES = [
    "home_attack", "home_defence", "home_elo",
    "away_attack", "away_defence", "away_elo",
    "elo_diff", "strength_expected_home_goals", "strength_expected_away_goals",
    "strength_expected_supremacy",
]


def strength_features(index: "StrengthIndex", home_team: str, away_team: str,
                      before_date: str) -> dict:
    """The P9 feature block for one fixture."""
    h = index.ratings_at(home_team, before_date)
    a = index.ratings_at(away_team, before_date)
    exp_h, exp_a = index.expected_goals(home_team, away_team, before_date)
    return {
        "home_attack": h["attack"],
        "home_defence": h["defence"],
        "home_elo": h["elo"],
        "away_attack": a["attack"],
        "away_defence": a["defence"],
        "away_elo": a["elo"],
        "elo_diff": h["elo"] - a["elo"],
        "strength_expected_home_goals": exp_h,
        "strength_expected_away_goals": exp_a,
        "strength_expected_supremacy": exp_h - exp_a,
    }
