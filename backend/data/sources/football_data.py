"""football-data.co.uk adapter — real per-match statistics.

Supplies the stat block the schema was designed around and the PulseLive
fixtures endpoint does not return: shots, shots on target, corners, fouls,
cards, and closing odds. Covers E0 (Premier League) and E1 (Championship),
which is also how promoted clubs arrive with real history.

This source is *enrichment*. PulseLive remains the source of truth for which
fixtures exist and what their status is — a miss here must never drop a fixture.
"""
from __future__ import annotations

import io

import pandas as pd
import requests

from .aliases import canonical_team, UnknownClubError

BASE_URL = "https://www.football-data.co.uk/mmz4281"
USER_AGENT = "Mozilla/5.0"

DIVISIONS = {"E0": "Premier League", "E1": "Championship"}

# football-data column -> our column. Left side is their published schema.
STAT_COLUMNS = {
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_ot",
    "AST": "away_shots_ot",
    "HC": "home_corners",
    "AC": "away_corners",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
}

ODDS_COLUMNS = {"B365H": "odds_home", "B365D": "odds_draw", "B365A": "odds_away"}


class SeasonFileUnavailable(Exception):
    """The season file is not published yet.

    Expected in-season: the current campaign's file can lag behind live fixtures.
    Callers should carry on with NULL statistics rather than treating it as fatal.
    """


def season_code(season_label: str) -> str:
    """'2025-26' -> '2526' (the path segment football-data.co.uk uses)."""
    start, end = season_label.split("-")
    return f"{start[-2:]}{end[-2:]}"


def _to_iso(value: str) -> str | None:
    """'15/08/2025' or '15/08/25' -> '2025-08-15'.

    The source publishes day-first dates; we store ISO so lexical order is
    chronological order. See docs/prompts/P1.
    """
    if not value or pd.isna(value):
        return None
    parsed = pd.to_datetime(str(value).strip(), dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def fetch_season(season_label: str, division: str = "E0", timeout: int = 60) -> pd.DataFrame:
    """Fetch and normalise one season-division file.

    Raises SeasonFileUnavailable when the file is not published.
    """
    if division not in DIVISIONS:
        raise ValueError(f"unknown division {division!r}; expected one of {list(DIVISIONS)}")

    url = f"{BASE_URL}/{season_code(season_label)}/{division}.csv"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)

    # The server answers 300 Multiple Choices with an HTML body for a file that
    # does not exist, so status alone is not a reliable signal.
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code != 200 or "html" in content_type.lower():
        raise SeasonFileUnavailable(
            f"{division} {season_label} not published (HTTP {resp.status_code}) at {url}"
        )

    df = pd.read_csv(io.StringIO(resp.content.decode("utf-8-sig", errors="replace")))
    return _normalise(df, season_label, division)


def _normalise(df: pd.DataFrame, season_label: str, division: str) -> pd.DataFrame:
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{division} {season_label} missing expected columns: {sorted(missing)}")

    df = df.dropna(subset=["HomeTeam", "AwayTeam"]).copy()

    out = pd.DataFrame()
    out["date"] = df["Date"].map(_to_iso)
    out["season"] = season_label
    out["division"] = division
    out["home_team"] = df["HomeTeam"].map(lambda n: canonical_team(n, strict=False))
    out["away_team"] = df["AwayTeam"].map(lambda n: canonical_team(n, strict=False))
    out["home_goals"] = pd.to_numeric(df["FTHG"], errors="coerce")
    out["away_goals"] = pd.to_numeric(df["FTAG"], errors="coerce")

    # Statistics: absent columns stay absent. Never substitute a default —
    # a fabricated measurement becomes training signal.
    for src, dest in STAT_COLUMNS.items():
        out[dest] = pd.to_numeric(df[src], errors="coerce") if src in df.columns else pd.NA

    for src, dest in ODDS_COLUMNS.items():
        out[dest] = pd.to_numeric(df[src], errors="coerce") if src in df.columns else pd.NA

    out["stats_source"] = "football-data.co.uk"

    # A row with no date cannot be joined or ordered, so it is unusable.
    return out.dropna(subset=["date"]).reset_index(drop=True)


def validate_clubs(df: pd.DataFrame) -> list[str]:
    """Return club names that do not resolve, for reporting rather than raising."""
    unknown = []
    for name in sorted(set(df["home_team"]) | set(df["away_team"])):
        try:
            canonical_team(name, strict=True)
        except UnknownClubError:
            unknown.append(name)
    return unknown
