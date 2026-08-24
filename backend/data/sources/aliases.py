"""Club name reconciliation between data sources.

The two sources disagree on a small number of club names. Canonical form is the
PulseLive `shortName`, because that is what the database and the frontend already
display — this map translates football-data.co.uk names into it.

Derived empirically by diffing the club sets of both sources rather than guessed:
of the clubs appearing in both, only two names differ.
"""
from __future__ import annotations

# football-data.co.uk name -> canonical (PulseLive shortName)
FOOTBALL_DATA_ALIASES = {
    "Man United": "Man Utd",
    "Tottenham": "Spurs",
    # Caught by the reconciliation report on the first live run: 38 unmatched
    # 2019-20 fixtures, all Sheffield United's. Exactly the failure the report
    # exists to surface rather than absorb.
    "Sheffield United": "Sheffield Utd",
}

# Championship clubs have no PulseLive entry while outside the Premier League,
# so their football-data name is already canonical. Listed explicitly so an
# unrecognised name is a loud failure rather than a silently invented club.
KNOWN_EFL_CLUBS = {
    "Birmingham", "Blackburn", "Bolton", "Bristol City", "Cardiff", "Charlton",
    "Coventry", "Derby", "Hull", "Ipswich", "Leicester", "Middlesbrough",
    "Millwall", "Norwich", "Oxford", "Portsmouth", "Preston", "QPR",
    "Sheffield United", "Sheffield Weds", "Southampton", "Stoke", "Swansea",
    "Watford", "West Brom", "Wrexham", "Blackpool", "Luton", "Plymouth",
    "Rotherham", "Huddersfield", "Reading", "Wigan", "Barnsley", "Peterboro",
    "Nott'm Forest", "Burnley", "West Ham", "Wolves", "Leeds", "Sunderland",
}


class UnknownClubError(ValueError):
    """Raised when a club name resolves to nothing recognised.

    Deliberately fatal: silently accepting an unknown name creates a phantom club
    with no history, which is the failure mode this rebuild exists to remove.
    """


def canonical_team(name: str, *, strict: bool = True) -> str:
    """Translate a source club name to its canonical form."""
    if name is None:
        raise UnknownClubError("club name is None")
    cleaned = str(name).strip()
    if not cleaned:
        raise UnknownClubError("club name is empty")

    resolved = FOOTBALL_DATA_ALIASES.get(cleaned, cleaned)

    if strict and resolved not in KNOWN_EFL_CLUBS and resolved not in _PL_CLUBS:
        raise UnknownClubError(
            f"unrecognised club {name!r} (resolved to {resolved!r}) — add it to "
            f"aliases.py rather than letting it through as a new team"
        )
    return resolved


# Premier League clubs seen across the seasons we ingest. Canonical spellings.
_PL_CLUBS = {
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley",
    "Chelsea", "Crystal Palace", "Everton", "Fulham", "Leeds", "Liverpool",
    "Man City", "Man Utd", "Newcastle", "Nott'm Forest", "Sheffield Utd",
    "Southampton", "Spurs", "Sunderland", "West Ham", "Wolves", "Leicester",
    "Watford", "Norwich", "West Brom", "Luton", "Ipswich", "Coventry", "Hull",
    "Huddersfield", "Cardiff", "Stoke", "Swansea", "Middlesbrough", "Brighton",
}


def all_known_clubs() -> set[str]:
    return _PL_CLUBS | KNOWN_EFL_CLUBS
