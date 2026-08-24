"""Load the baked snapshot into whatever database is configured.

`entrypoint.sh` restores a SQLite *file*, which means nothing when DATABASE_URL
points at Postgres. This does the same job at the SQL layer: if the target is
empty, read `backend/seed/epl.db` and copy its rows across.

The property being preserved is why the snapshot exists at all — a cold instance
answers /predict immediately instead of spending minutes rebuilding from the
Premier League API and returning 503 in the meantime.

On Postgres this runs exactly once, ever, because the data then persists. That is
also what stops visitors' predictions being wiped on every restart, which is what
the ephemeral disk was doing.
"""
from __future__ import annotations

import os
import sqlite3

from sqlalchemy import func, inspect, text

from db.database import Backtest, MatchResult, SessionLocal, engine

SEED_DIR = os.environ.get("SEED_DIR", "/app/seed")
SEED_DB = os.path.join(SEED_DIR, "epl.db")

# (table, model) in insertion order. match_results first: everything else is
# derived from it, so a partial load is less confusing this way round.
TABLES = [("match_results", MatchResult), ("backtests", Backtest)]

CHUNK = 500


def _seed_available() -> bool:
    return os.path.isfile(SEED_DB)


def _target_is_empty(db) -> bool:
    return (db.query(func.count(MatchResult.id)).scalar() or 0) == 0


def load_snapshot_if_empty() -> dict:
    """Copy the snapshot into the configured database when it holds no matches."""
    report = {"loaded": False, "tables": {}, "reason": None}

    if not _seed_available():
        report["reason"] = f"no snapshot at {SEED_DB}"
        print(f"[seed] {report['reason']} — the database will be rebuilt from the network")
        return report

    db = SessionLocal()
    try:
        if not _target_is_empty(db):
            report["reason"] = "database already has matches"
            return report
    finally:
        db.close()

    print(f"[seed] empty database — loading snapshot from {SEED_DB}")
    source = sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        with engine.begin() as conn:
            for table, model in TABLES:
                # Only columns the destination actually has. The snapshot is
                # written by whichever version last refreshed it, so it can carry
                # a column this build has dropped — copying blind would fail the
                # whole load for a field nothing reads.
                dest_cols = {c["name"] for c in inspect(engine).get_columns(table)}
                try:
                    src_cols = [r[1] for r in source.execute(f"PRAGMA table_info({table})")]
                except sqlite3.Error:
                    continue
                cols = [c for c in src_cols if c in dest_cols and c != "id"]
                if not cols:
                    continue

                rows = source.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
                if not rows:
                    continue

                stmt = text(
                    f"INSERT INTO {table} ({', '.join(cols)}) "
                    f"VALUES ({', '.join(':' + c for c in cols)})"
                )
                for start in range(0, len(rows), CHUNK):
                    conn.execute(stmt, [dict(zip(cols, r)) for r in rows[start:start + CHUNK]])
                report["tables"][table] = len(rows)
                print(f"[seed]   {table}: {len(rows)} rows")
    finally:
        source.close()

    # Postgres sequences do not advance for explicitly-supplied ids, and they do
    # not here either since `id` is excluded — but a snapshot loaded into a table
    # whose sequence was already touched would collide. Resetting is cheap and
    # makes the load safe to repeat against a partially-populated database.
    _resync_sequences()

    report["loaded"] = True
    return report


def _resync_sequences() -> None:
    """Point each Postgres identity sequence past the highest existing id."""
    from db.database import IS_SQLITE

    if IS_SQLITE:
        return
    with engine.begin() as conn:
        for table, _ in TABLES:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            ))
