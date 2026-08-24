"""Reconcile football-data.co.uk statistics onto the PulseLive fixture spine.

PulseLive decides which fixtures exist; this module attaches the statistics that
endpoint cannot supply. Every join outcome is counted and reported — an unmatched
fixture is a finding to surface, never a row to quietly default.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from db.database import SessionLocal, MatchResult
from .sources import fetch_season, validate_clubs, SeasonFileUnavailable

# Kickoff is stored in UTC while football-data publishes UK local dates, so a
# late kickoff can land on either side of midnight. Allow a one-day window.
DATE_TOLERANCE_DAYS = 1

STAT_FIELDS = [
    "home_shots", "away_shots",
    "home_shots_ot", "away_shots_ot",
    "home_corners", "away_corners",
    "home_fouls", "away_fouls",
    "home_yellow_cards", "away_yellow_cards",
    "home_red_cards", "away_red_cards",
]


def _nearby_dates(iso_date: str) -> list[str]:
    base = datetime.strptime(iso_date, "%Y-%m-%d")
    return [
        (base + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(-DATE_TOLERANCE_DAYS, DATE_TOLERANCE_DAYS + 1)
    ]


def _index_stats(df) -> dict:
    """Index source rows by (home, away, date) for tolerant lookup."""
    index = {}
    for row in df.itertuples():
        index[(row.home_team, row.away_team, row.date)] = row
    return index


def _coerce(value):
    """Source cell -> int or None. Never a default."""
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


def enrich_season(db, season_label: str, division: str = "E0") -> dict:
    """Attach statistics to one season's stored fixtures. Returns a report."""
    report = {
        "season": season_label,
        "division": division,
        "fixtures_in_db": 0,
        "matched": 0,
        "unmatched": 0,
        "unmatched_examples": [],
        "unknown_clubs": [],
        "status": "ok",
    }

    try:
        source_df = fetch_season(season_label, division)
    except SeasonFileUnavailable as exc:
        # Expected for the in-progress season: statistics simply are not
        # published yet. Fixtures and goals remain valid from PulseLive.
        report["status"] = "source_unavailable"
        report["detail"] = str(exc)
        return report

    report["unknown_clubs"] = validate_clubs(source_df)
    index = _index_stats(source_df)

    # Scoped to the division being enriched. Unscoped, this walked every row in the
    # season — so once the Championship was ingested, enriching E0 iterated 932
    # fixtures against a 380-row Premier League file and reported 552 of them
    # "unmatched". Worse, the loop below WRITES `fixture.division`, so an unscoped
    # query is one coincidental name/date collision away from relabelling a
    # second-tier match as top-flight.
    fixtures = (
        db.query(MatchResult)
        .filter(MatchResult.season == season_label, MatchResult.division == division)
        .all()
    )
    report["fixtures_in_db"] = len(fixtures)

    for fixture in fixtures:
        if not fixture.date:
            continue
        match = None
        for candidate_date in _nearby_dates(fixture.date):
            match = index.get((fixture.home_team, fixture.away_team, candidate_date))
            if match is not None:
                break

        if match is None:
            report["unmatched"] += 1
            if len(report["unmatched_examples"]) < 10:
                report["unmatched_examples"].append(
                    f"{fixture.date} {fixture.home_team} v {fixture.away_team}"
                )
            continue

        for field in STAT_FIELDS:
            setattr(fixture, field, _coerce(getattr(match, field, None)))
        fixture.stats_source = "football-data.co.uk"
        fixture.division = division
        report["matched"] += 1

    db.commit()
    return report


def enrich_all(season_labels: list[str], division: str = "E0") -> list[dict]:
    """Enrich every season and print a reconciliation report."""
    db = SessionLocal()
    reports = []
    try:
        for season in season_labels:
            report = enrich_season(db, season, division)
            reports.append(report)
            _print_report(report)
    finally:
        db.close()
    _print_summary(reports)
    return reports


def _print_report(report: dict) -> None:
    if report["status"] == "source_unavailable":
        print(f"  {report['season']}: statistics not published yet — goals retained, stats NULL")
        return

    total = report["fixtures_in_db"]
    matched = report["matched"]
    pct = (matched / total * 100) if total else 0.0
    print(f"  {report['season']}: {matched}/{total} matched ({pct:.1f}%), {report['unmatched']} unmatched")

    for example in report["unmatched_examples"]:
        print(f"      unmatched: {example}")
    if report["unknown_clubs"]:
        print(f"      unknown clubs: {report['unknown_clubs']}")


def _print_summary(reports: list[dict]) -> None:
    total = sum(r["fixtures_in_db"] for r in reports)
    matched = sum(r["matched"] for r in reports)
    pct = (matched / total * 100) if total else 0.0
    print(f"Statistics coverage: {matched}/{total} fixtures ({pct:.1f}%)")
