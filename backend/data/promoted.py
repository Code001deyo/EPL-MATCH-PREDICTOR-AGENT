"""Championship history for clubs with no Premier League record.

A club is a permanent entity. Relegation does not delete its history, and
promotion does not create a club from nothing — a promoted side has a full
season of recent competitive football behind it, in another division.

Without this, `_team_rolling()` returns all-zero features for a promoted club,
which the model reads as a team that neither scores nor concedes. See
docs/prompts/P3.
"""
from __future__ import annotations

from db.database import SessionLocal, MatchResult
from .sources import fetch_season, SeasonFileUnavailable

# How many prior Championship seasons to carry for a club with no top-flight
# record. Two gives a usable rolling window at matchweek 1 without reaching back
# into football too old to be comparable.
EFL_HISTORY_SEASONS = 2


def clubs_missing_history(db, season_label: str) -> set[str]:
    """Clubs playing this season that have no match history before it."""
    current = db.query(MatchResult).filter(MatchResult.season == season_label).all()
    clubs = {m.home_team for m in current} | {m.away_team for m in current}

    prior_rows = (
        db.query(MatchResult.home_team, MatchResult.away_team)
        .filter(MatchResult.season != season_label)
        .all()
    )
    with_history = {r[0] for r in prior_rows} | {r[1] for r in prior_rows}

    return clubs - with_history


def prior_season_labels(season_label: str, count: int = EFL_HISTORY_SEASONS) -> list[str]:
    start = int(season_label.split("-")[0])
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(start - count, start)]


def ingest_efl_history(season_label: str, clubs: set[str] | None = None) -> dict:
    """Store Championship matches involving clubs that lack Premier League history.

    Only matches *involving* those clubs are kept — the rest of the Championship
    is not relevant to predicting Premier League fixtures.
    """
    db = SessionLocal()
    report = {"season": season_label, "clubs": [], "seasons_fetched": [], "matches_added": 0}

    try:
        targets = clubs if clubs is not None else clubs_missing_history(db, season_label)
        report["clubs"] = sorted(targets)
        if not targets:
            print("Every club has prior history; no Championship backfill needed.")
            return report

        print(f"Clubs with no prior history: {sorted(targets)}")

        for efl_season in prior_season_labels(season_label):
            try:
                df = fetch_season(efl_season, "E1")
            except SeasonFileUnavailable as exc:
                print(f"  E1 {efl_season} unavailable: {exc}")
                continue

            relevant = df[df["home_team"].isin(targets) | df["away_team"].isin(targets)]
            if relevant.empty:
                continue

            existing = {
                (m.date, m.home_team, m.away_team)
                for m in db.query(MatchResult).filter(MatchResult.season == efl_season).all()
            }

            added = 0
            for row in relevant.itertuples():
                if (row.date, row.home_team, row.away_team) in existing:
                    continue
                if row.home_goals != row.home_goals or row.away_goals != row.away_goals:
                    continue  # unplayed
                db.add(MatchResult(
                    season=efl_season,
                    matchweek=0,          # E1 files carry no gameweek; ordering is by date
                    date=row.date,
                    division="E1",
                    stats_source="football-data.co.uk",
                    home_team=row.home_team,
                    away_team=row.away_team,
                    home_goals=int(row.home_goals),
                    away_goals=int(row.away_goals),
                    home_shots=_opt(row.home_shots),
                    away_shots=_opt(row.away_shots),
                    home_shots_ot=_opt(row.home_shots_ot),
                    away_shots_ot=_opt(row.away_shots_ot),
                    home_corners=_opt(row.home_corners),
                    away_corners=_opt(row.away_corners),
                    home_fouls=_opt(row.home_fouls),
                    away_fouls=_opt(row.away_fouls),
                    home_yellow_cards=_opt(row.home_yellow_cards),
                    away_yellow_cards=_opt(row.away_yellow_cards),
                    home_red_cards=_opt(row.home_red_cards),
                    away_red_cards=_opt(row.away_red_cards),
                ))
                added += 1

            db.commit()
            report["seasons_fetched"].append(efl_season)
            report["matches_added"] += added
            print(f"  E1 {efl_season}: added {added} matches involving promoted clubs")

    finally:
        db.close()

    return report


def _opt(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
