"""Point-in-time index over the match history.

## Why this exists

Every window helper in `features.py` used to take the whole match frame and
filter it with a boolean mask — `df[(df["home_team"] == team) & (df["date"] <
before)]` — then read `.tail(5)` off the result. One fixture's feature vector
needs about a dozen of those, and a training build does it for every Premier
League match in the database.

Measured on the deployed dataset (11,218 matches, 4,570 of them training
targets) that is roughly 55,000 full-frame scans. The production retrain sat on
`stage: "building feature matrix"` for fifteen minutes before the first
estimator was fitted, which is what an operator saw as "training never starts".
Locally, on 6,545 matches, `build_training_matrix` took 356 seconds.

None of that scanning was necessary. The frame is already in chronological
order, so the rows a team-scoped helper may see are a **prefix** of that team's
own rows: everything up to the first date not earlier than the fixture's. That
is a binary search into a sorted array, and the windows the helpers read are the
last five or ten entries of the prefix. This module groups the frame once and
serves numpy slices afterwards.

## Why the results are identical, not approximate

- A club plays at most one match per day, so ordering a team's rows by their
  position in the date-ordered frame gives exactly the sequence the old
  concat-then-stable-sort produced.
- The cut is `searchsorted(dates, before_date, side="left")`, which counts dates
  strictly less than the fixture's — the same predicate as `df["date"] <
  before_date`, on the same ISO strings, so the no-leakage guarantee is
  unchanged and still enforced by comparison rather than by convention.
- Only the last `LONGEST_ROLLING_WINDOW` matches can reach any output, so a
  window lookup returns at most that many rows — the same truncation argument
  `_team_rolling` already documented.
- Counts that genuinely need the whole history (`played`, `top_flight`) are
  read off a cumulative sum, not recomputed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as _date
from typing import NamedTuple

import numpy as np
import pandas as pd

TOP_FLIGHT = "E0"

# The longest window any rolling feature reads. Only this many of a team's most
# recent matches can affect an output, so a lookup never returns more.
LONGEST_ROLLING_WINDOW = 10

_ORDINALS: dict = {}


def date_ordinal(value) -> float:
    """Day number for an ISO date string; NaN when it will not parse.

    Memoised because the old code called `pd.to_datetime` once per fixture per
    feature: `guess_datetime_format` alone accounted for 20 of the 356 seconds a
    local feature build took, re-parsing a few thousand distinct dates tens of
    thousands of times.
    """
    cached = _ORDINALS.get(value) if isinstance(value, str) else None
    if cached is not None:
        return cached
    try:
        result = float(_date.fromisoformat(value).toordinal())
    except (TypeError, ValueError, AttributeError):
        try:
            result = float(pd.Timestamp(value).toordinal())
        except Exception:
            result = float("nan")
    if isinstance(value, str):
        _ORDINALS[value] = result
    return result


def shift_iso(value, days: int):
    """`value` minus `days`, as an ISO string. None when `value` will not parse."""
    ordinal = date_ordinal(value)
    if ordinal != ordinal:      # NaN
        return None
    return _date.fromordinal(int(ordinal) - days).isoformat()


class TeamWindow(NamedTuple):
    """What a team-scoped feature may see at one fixture's kickoff.

    The arrays hold the team's most recent `LONGEST_ROLLING_WINDOW` matches
    before the cut, oldest first — so `[-5:]` is the five-match window and
    `[-10:]` the ten-match one, exactly the rows `.tail(n)` used to select.
    `played` and `top_flight` count the full history, which the windows cannot.
    """
    played: int
    top_flight: int
    last_date: object
    gf: np.ndarray
    ga: np.ndarray
    sot: np.ndarray
    shots: np.ndarray
    corners: np.ndarray
    fouls: np.ndarray
    yellows: np.ndarray
    pts: np.ndarray
    cs: np.ndarray
    btts: np.ndarray
    over25: np.ndarray


_EMPTY = np.empty(0, dtype=float)
EMPTY_WINDOW = TeamWindow(0, 0, None, *([_EMPTY] * 11))


class _TeamRows(NamedTuple):
    dates: np.ndarray
    gf: np.ndarray
    ga: np.ndarray
    sot: np.ndarray
    shots: np.ndarray
    corners: np.ndarray
    fouls: np.ndarray
    yellows: np.ndarray
    pts: np.ndarray
    cs: np.ndarray
    btts: np.ndarray
    over25: np.ndarray
    e0_cum: np.ndarray          # e0_cum[k] = top-flight matches among the first k
    home: tuple                 # (dates, gf, ga) for this club's home matches
    away: tuple                 # (dates, gf, ga) for its away matches


class _PairRows(NamedTuple):
    dates: np.ndarray
    total_goals: np.ndarray
    first_won: np.ndarray       # 1.0 where the alphabetically first club won
    second_won: np.ndarray


def _floats(df: pd.DataFrame, column: str) -> np.ndarray:
    """A float column, or all-NaN when the frame does not carry it.

    Missing stays missing: an absent measurement becomes NaN for XGBoost to
    split on, never a substituted constant.
    """
    if column not in df.columns:
        return np.full(len(df), np.nan)
    return pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)


class MatchHistory:
    """Chronological history grouped by club and by fixture pairing.

    Built once per feature build — a single pass over the frame — and then
    queried per fixture. Every lookup is point-in-time regardless of when the
    index was constructed, because the cut is made from the fixture's own date.
    """

    def __init__(self, df: pd.DataFrame):
        self._teams: dict[str, _TeamRows] = {}
        self._pairs: dict[tuple, _PairRows] = {}
        if df is None or len(df) == 0:
            return
        self._build(df)

    # ----------------------------------------------------------------- build

    def _build(self, df: pd.DataFrame) -> None:
        dates = df["date"].to_numpy(dtype=object)
        home_team = df["home_team"].to_numpy(dtype=object)
        away_team = df["away_team"].to_numpy(dtype=object)
        hg, ag = _floats(df, "home_goals"), _floats(df, "away_goals")

        stats = {
            side: {name: _floats(df, f"{side}_{col}") for name, col in (
                ("sot", "shots_ot"), ("shots", "shots"), ("corners", "corners"),
                ("fouls", "fouls"), ("yellows", "yellow_cards"))}
            for side in ("home", "away")
        }
        # Venue-independent by definition: both read the raw goal columns.
        btts = ((hg > 0) & (ag > 0)).astype(float)
        over25 = ((hg + ag) > 2).astype(float)
        if "division" in df.columns:
            is_e0 = (df["division"].fillna(TOP_FLIGHT) == TOP_FLIGHT).to_numpy(dtype=float)
        else:
            is_e0 = np.zeros(len(df))

        positions: dict = defaultdict(list)
        at_home: dict = defaultdict(list)
        pair_positions: dict = defaultdict(list)
        pair_first_home: dict = defaultdict(list)
        for i in range(len(df)):
            h, a = home_team[i], away_team[i]
            positions[h].append(i)
            at_home[h].append(True)
            positions[a].append(i)
            at_home[a].append(False)
            key = (h, a) if h <= a else (a, h)
            pair_positions[key].append(i)
            pair_first_home[key].append(h == key[0])

        for team, pos in positions.items():
            idx = np.asarray(pos, dtype=int)
            home = np.asarray(at_home[team], dtype=bool)
            self._teams[team] = self._team_rows(
                idx, home, dates, hg, ag, stats, btts, over25, is_e0)

        for key, pos in pair_positions.items():
            idx = np.asarray(pos, dtype=int)
            first_home = np.asarray(pair_first_home[key], dtype=bool)
            fh, fa = hg[idx], ag[idx]
            self._pairs[key] = _PairRows(
                dates=dates[idx],
                total_goals=fh + fa,
                first_won=np.where(first_home, fh > fa, fa > fh).astype(float),
                second_won=np.where(first_home, fa > fh, fh > fa).astype(float),
            )

    @staticmethod
    def _team_rows(idx, home, dates, hg, ag, stats, btts, over25, is_e0) -> _TeamRows:
        gf = np.where(home, hg[idx], ag[idx])
        ga = np.where(home, ag[idx], hg[idx])
        pick = {name: np.where(home, stats["home"][name][idx], stats["away"][name][idx])
                for name in stats["home"]}
        # NaN goals compare false both ways and so score 0 — the same value the
        # `np.where(gf > ga, 3, np.where(gf == ga, 1, 0))` chain produced.
        home_idx = idx[home]
        away_idx = idx[~home]
        return _TeamRows(
            dates=dates[idx],
            gf=gf, ga=ga,
            sot=pick["sot"], shots=pick["shots"], corners=pick["corners"],
            fouls=pick["fouls"], yellows=pick["yellows"],
            pts=np.where(gf > ga, 3.0, np.where(gf == ga, 1.0, 0.0)),
            cs=(ga == 0).astype(float),
            btts=btts[idx], over25=over25[idx],
            e0_cum=np.concatenate(([0.0], np.cumsum(is_e0[idx]))),
            home=(dates[home_idx], hg[home_idx], ag[home_idx]),
            away=(dates[away_idx], ag[away_idx], hg[away_idx]),
        )

    # ---------------------------------------------------------------- lookup

    @staticmethod
    def _cut(dates: np.ndarray, before_date) -> int:
        """How many of `dates` fall strictly before `before_date`."""
        return int(np.searchsorted(dates, before_date, side="left"))

    def teams(self):
        return self._teams.keys()

    def team_window(self, team: str, before_date, keep: int = LONGEST_ROLLING_WINDOW) -> TeamWindow:
        rows = self._teams.get(team)
        if rows is None:
            return EMPTY_WINDOW
        k = self._cut(rows.dates, before_date)
        if k == 0:
            return EMPTY_WINDOW
        lo = max(0, k - keep)
        return TeamWindow(
            played=k,
            top_flight=int(rows.e0_cum[k]),
            last_date=rows.dates[k - 1],
            gf=rows.gf[lo:k], ga=rows.ga[lo:k],
            sot=rows.sot[lo:k], shots=rows.shots[lo:k],
            corners=rows.corners[lo:k], fouls=rows.fouls[lo:k],
            yellows=rows.yellows[lo:k],
            pts=rows.pts[lo:k], cs=rows.cs[lo:k],
            btts=rows.btts[lo:k], over25=rows.over25[lo:k],
        )

    def venue_window(self, team: str, venue: str, before_date, window: int = 5):
        """(goals for, goals against) over the club's last `window` matches at
        this venue. Two empty arrays when it has never played there."""
        rows = self._teams.get(team)
        if rows is None:
            return _EMPTY, _EMPTY
        dates, gf, ga = rows.home if venue == "home" else rows.away
        k = self._cut(dates, before_date)
        lo = max(0, k - window)
        return gf[lo:k], ga[lo:k]

    def h2h_window(self, home_team: str, away_team: str, before_date, window: int = 5):
        """(total goals per meeting, wins by the fixture's home side) over the
        pair's last `window` meetings, either way round."""
        key = (home_team, away_team) if home_team <= away_team else (away_team, home_team)
        rows = self._pairs.get(key)
        if rows is None:
            return _EMPTY, 0
        k = self._cut(rows.dates, before_date)
        if k == 0:
            return _EMPTY, 0
        lo = max(0, k - window)
        wins = rows.first_won if home_team == key[0] else rows.second_won
        return rows.total_goals[lo:k], int(wins[lo:k].sum())

    def matches_within(self, team: str, before_date, days: int) -> float:
        """Fixture congestion: matches played in the `days` before this one."""
        cutoff = shift_iso(before_date, days)
        if cutoff is None:
            return np.nan
        rows = self._teams.get(team)
        if rows is None:
            return 0.0
        return float(self._cut(rows.dates, before_date) - self._cut(rows.dates, cutoff))
