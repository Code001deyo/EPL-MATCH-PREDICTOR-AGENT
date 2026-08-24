"""Full Championship (E1) seasons, as a league in their own right.

Until now `match_results` held only a *fragment* of the Championship: `promoted.py`
pulls the matches involving clubs about to be promoted, so a newly-promoted side has
real prior form instead of NaN on matchday one. That is roughly 90 rows of a
552-match season, and it exists to seed features — it was never a league.

Reporting a table from that fragment would be worse than reporting nothing: the
clubs are real, the matches are real, and the standings would be entirely wrong,
because most of each club's season is missing. So this module ingests the complete
season instead, and the two divisions are then reported side by side.

Completing the data also changes model inputs. `strength.py` uses Championship rates
to seed a promoted club's first top-flight attack/defence rating and its starting
Elo; with a full season behind it that seed is computed from 46 matches rather than
whichever handful the fragment happened to contain. That is an improvement, but it
is a change — it takes effect only on the next retrain, and the metric delta should
be reported rather than absorbed.
"""
from __future__ import annotations

import pandas as pd

from data.sources.football_data import SeasonFileUnavailable, fetch_season
from db.database import MatchResult, SessionLocal

DIVISION = "E1"
# 24 clubs, so a complete round of the division is 12 matches.
MATCHES_PER_ROUND = 12
COMPLETE_SEASON_MATCHES = 552   # 24 clubs x 46 rounds


def _opt(value):
    """NaN -> None. Missing means missing; never substitute a zero."""
    if value is None or value != value:
        return None
    return int(value)


def derive_matchweeks(df: pd.DataFrame) -> pd.Series:
    """Assign a round number to each E1 fixture.

    football-data.co.uk files carry no gameweek column — which is why every
    Championship row currently sits at `matchweek=0`, breaking any per-matchweek
    chart. The round is therefore derived: fixtures are ordered by date and cut
    into blocks of twelve.

    This is an approximation and is labelled as one wherever it surfaces. A
    postponed fixture rejoins the calendar late and lands in a later block than the
    round it truly belonged to. It is accurate enough to trend goals over a season
    and is not used for anything that requires exact round membership — the league
    table does not depend on it at all.
    """
    order = df.sort_values("date", kind="stable").index
    rounds = pd.Series(range(len(order)), index=order) // MATCHES_PER_ROUND + 1
    return rounds.reindex(df.index)


def seed_championship(season_labels: list[str], db=None) -> list[dict]:
    """Ingest complete E1 seasons, filling in around any fragment already stored.

    Existing rows are matched on (season, date, home, away) and left alone rather
    than deleted and rewritten: the fragment rows carry reconciled statistics and
    re-inserting them would drop those, which is precisely the destructive-refresh
    bug fixed earlier in ingestion.py.
    """
    owns_session = db is None
    db = db or SessionLocal()
    reports = []
    try:
        for season in season_labels:
            report = {"season": season, "division": DIVISION, "added": 0,
                      "already_present": 0, "status": "ok"}
            try:
                df = fetch_season(season, DIVISION)
            except SeasonFileUnavailable as exc:
                report["status"] = f"unavailable: {exc}"
                reports.append(report)
                continue

            df = df.dropna(subset=["home_goals", "away_goals"]).reset_index(drop=True)
            if df.empty:
                report["status"] = "no played matches"
                reports.append(report)
                continue

            df["matchweek"] = derive_matchweeks(df)

            existing = {
                (m.date, m.home_team, m.away_team)
                for m in db.query(MatchResult).filter(
                    MatchResult.season == season, MatchResult.division == DIVISION
                ).all()
            }

            for row in df.itertuples():
                key = (row.date, row.home_team, row.away_team)
                if key in existing:
                    report["already_present"] += 1
                    continue
                db.add(MatchResult(
                    season=season,
                    matchweek=int(row.matchweek),
                    date=row.date,
                    division=DIVISION,
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
                report["added"] += 1

            db.commit()

            # The fragment rows predate this module and sit at matchweek 0, which
            # would leave a phantom "round 0" in every chart. Give them the round
            # their date implies, now that the surrounding season exists.
            _backfill_fragment_matchweeks(db, season)

            total = db.query(MatchResult).filter(
                MatchResult.season == season, MatchResult.division == DIVISION
            ).count()
            report["total"] = total
            report["complete"] = total >= COMPLETE_SEASON_MATCHES
            reports.append(report)
            print(f"  E1 {season}: +{report['added']} added, {total} total"
                  f"{'' if report['complete'] else ' (in progress or partial)'}")
    finally:
        if owns_session:
            db.close()
    return reports


def _backfill_fragment_matchweeks(db, season: str) -> int:
    """Re-derive rounds for a season's E1 rows that were stored without one."""
    rows = db.query(MatchResult).filter(
        MatchResult.season == season, MatchResult.division == DIVISION
    ).all()
    if not rows:
        return 0
    frame = pd.DataFrame([{"id": r.id, "date": r.date} for r in rows]).set_index("id")
    rounds = derive_matchweeks(frame)
    fixed = 0
    for row in rows:
        want = int(rounds.loc[row.id])
        if row.matchweek != want:
            row.matchweek = want
            fixed += 1
    if fixed:
        db.commit()
    return fixed
