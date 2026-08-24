"""External data source adapters."""
from .aliases import canonical_team, all_known_clubs, UnknownClubError
from .football_data import (
    DIVISIONS,
    SeasonFileUnavailable,
    fetch_season,
    season_code,
    validate_clubs,
)

__all__ = [
    "canonical_team",
    "all_known_clubs",
    "UnknownClubError",
    "DIVISIONS",
    "SeasonFileUnavailable",
    "fetch_season",
    "season_code",
    "validate_clubs",
]
