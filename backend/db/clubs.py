"""Club identity: the ids needed to show a real badge.

The site drew its own monogram shields because Premier League club crests are
trademarked and there is no openly licensed set of them. The instruction now is
to use the real badges, for a non-commercial project. That does not make the
crests un-trademarked, so the decision is recorded rather than hidden: this
stores the identifiers the official badge CDN keys on, and the frontend points an
`<img>` at it. Nothing is copied into the repository, and switching back to drawn
badges is one component away.

The badge URL needs an **Opta** id (`t3`), which is not the id PulseLive uses in
its fixture payloads (Arsenal is `1` there). It comes from
`/teams?compSeasons=…`, in `altIds.opta`, so it is fetched and stored rather than
hardcoded — a hardcoded map goes wrong the summer three clubs are promoted, and
goes wrong silently, as a club rendering with the wrong badge.

Keyed by `short_name`, because that is the name `match_results`, `fixtures` and
every router already speak.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Text

from db.database import Base

# The official badge, by Opta id. `.svg` scales to any size and is a fifth of the
# weight of the 2x PNG.
BADGE_URL = "https://resources.premierleague.com/premierleague/badges/{opta}.svg"


class Club(Base):
    """One club, and the ids that identify it outside this database."""

    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True, index=True)

    # The name used everywhere else in the schema: PulseLive's `shortName`.
    short_name = Column(Text, unique=True, index=True, nullable=False)
    name = Column(Text)
    abbr = Column(Text)               # "ARS" — PulseLive's own three-letter code

    pl_team_id = Column(Integer, index=True)   # PulseLive team id (Arsenal = 1)
    opta_id = Column(Text)                     # "t3" — what the badge CDN wants

    updated_at = Column(Text)


def badge_url(opta_id: str | None) -> str | None:
    """The official badge for a club, or None when its Opta id is unknown.

    None, not a placeholder image: a club whose id is missing should fall back to
    the drawn monogram, which at least says which club it is, rather than to a
    grey square that says nothing.
    """
    return BADGE_URL.format(opta=opta_id) if opta_id else None


def upsert_clubs(db, rows: list[dict]) -> dict:
    """Insert or update clubs by `short_name`. Returns counts."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = updated = 0

    existing = {c.short_name: c for c in db.query(Club).all()}

    for row in rows:
        club = existing.get(row["short_name"])
        if club is None:
            db.add(Club(**row, updated_at=now))
            existing[row["short_name"]] = club
            inserted += 1
            continue
        changed = False
        for field, value in row.items():
            # Never overwrite a known id with a missing one. A season's payload
            # that happens to omit altIds must not erase a badge that works.
            if value in (None, "") and getattr(club, field) not in (None, ""):
                continue
            if getattr(club, field) != value:
                setattr(club, field, value)
                changed = True
        if changed:
            club.updated_at = now
            updated += 1

    db.commit()
    return {"inserted": inserted, "updated": updated, "total": len(rows)}


def all_clubs(db) -> list[dict]:
    """Every club known, with its badge URL resolved."""
    return [
        {
            "short_name": c.short_name,
            "name": c.name,
            "abbr": c.abbr,
            "opta_id": c.opta_id,
            "badge_url": badge_url(c.opta_id),
        }
        for c in db.query(Club).order_by(Club.short_name.asc()).all()
    ]
