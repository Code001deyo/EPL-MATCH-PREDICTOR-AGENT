"""What the committed seed database is not allowed to contain.

`backend/seed/epl.db` is a deliberate, committed snapshot: match history and
trained models baked into the image so a host with no persistent disk comes up
working instead of untrained. On a public repository that snapshot is published
to everyone.

It is clean today only by accident of timing - it was generated before the
`subscribers` and `admin_users` tables existed. Regenerate it from a live
database now and the next push would publish real email addresses, confirmation
tokens and an admin password hash. Nothing in the build would object.

So the rule is written down rather than remembered: these tables must not be in
the seed, and `pii_tables` is the check. It reads the file directly with sqlite3
rather than through SQLAlchemy, because the question is what is *in the file*,
not what the application's models say should be.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Tables that hold personal data or credentials. A table added later that holds
# either belongs on this list on the same commit that creates it.
FORBIDDEN = (
    "subscribers",
    "notification_log",
    "admin_users",
    "admin_sessions",
    "password_resets",
)

SEED_DB = Path(__file__).resolve().parent.parent / "seed" / "epl.db"


def pii_tables(db_path) -> list[str]:
    """Forbidden tables present in the SQLite file at `db_path`, sorted.

    An empty list is the only acceptable answer for anything committed.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(path)

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        present = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    return sorted(present & set(FORBIDDEN))
