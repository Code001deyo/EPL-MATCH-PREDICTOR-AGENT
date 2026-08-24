from sqlalchemy import create_engine, Column, Integer, Text, event
from sqlalchemy.types import Float as Real
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import text

import os

# Container default; override with DATA_DIR to run the API outside Docker.
DATA_DIR = os.environ.get("DATA_DIR", "/app/dbdata")
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'epl.db')}"
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """Configure SQLite for concurrent readers on every new connection.

    Measured before this existed: ten simultaneous POST /predict returned
    0 successes and 10 x HTTP 500, all `sqlite3.OperationalError: database is
    locked`. Every prediction writes a row, and the default `journal_mode=delete`
    takes an exclusive lock across the whole database for each write, so ten
    writers serialise onto a lock the losers give up on.

    WAL is the actual fix: writers append to a separate log, so readers never
    block on a write and a write never blocks a read. `busy_timeout` covers the
    remaining case — writers still serialise against each other, and 15s is far
    longer than the ~1s a prediction insert takes, so a queued writer waits its
    turn instead of failing.

    `synchronous=NORMAL` is safe under WAL: a crash can lose the last commits but
    cannot corrupt the file, and on a host with an ephemeral disk the database is
    rebuilt from the baked snapshot anyway.

    These are per-connection settings, hence the event hook. journal_mode is the
    exception — it is persistent in the file — but setting it every time is
    harmless and means a database restored from the seed snapshot is migrated to
    WAL on first use rather than staying in delete mode forever.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class MatchResult(Base):
    __tablename__ = "match_results"
    id = Column(Integer, primary_key=True, index=True)
    season = Column(Text)
    matchweek = Column(Integer)
    # ISO 8601 'YYYY-MM-DD'. Must stay ISO: every rolling window in
    # data/features.py orders and filters on this column lexically, which is
    # only chronological in ISO form. See docs/prompts/P1.
    date = Column(Text, index=True)
    division = Column(Text, default="E0")   # E0 = Premier League, E1 = Championship
    stats_source = Column(Text, nullable=True)  # provenance: which source filled the stat block
    home_team = Column(Text)
    away_team = Column(Text)
    home_goals = Column(Integer)
    away_goals = Column(Integer)
    home_xg = Column(Real)
    away_xg = Column(Real)
    home_shots_ot = Column(Integer)
    away_shots_ot = Column(Integer)
    home_possession = Column(Real)
    away_possession = Column(Real)
    home_shots = Column(Integer, nullable=True)
    away_shots = Column(Integer, nullable=True)
    home_corners = Column(Integer, nullable=True)
    away_corners = Column(Integer, nullable=True)
    home_fouls = Column(Integer, nullable=True)
    away_fouls = Column(Integer, nullable=True)
    home_yellow_cards = Column(Integer, nullable=True)
    away_yellow_cards = Column(Integer, nullable=True)
    home_red_cards = Column(Integer, nullable=True)
    away_red_cards = Column(Integer, nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    fixture = Column(Text)
    season = Column(Text)
    matchweek = Column(Integer)
    predicted_home = Column(Integer)
    predicted_away = Column(Integer)
    home_win_prob = Column(Real)
    draw_prob = Column(Real)
    away_win_prob = Column(Real)
    confidence = Column(Real)
    key_drivers = Column(Text)
    actual_home = Column(Integer, nullable=True)
    actual_away = Column(Integer, nullable=True)
    predicted_stats = Column(Text, nullable=True)
    created_at = Column(Text)
    # A fixture has ONE prediction. Re-predicting updates it in place, so these
    # record that it happened rather than letting a second row appear in History.
    updated_at = Column(Text, nullable=True)
    times_predicted = Column(Integer, default=1)


class Backtest(Base):
    """Walk-forward backtest predictions — a model refit before each matchweek,
    scored against the real result. Distinct from `predictions`: those rows are
    whatever fixtures a user happened to ask about via the UI; these are a
    systematic simulation over every completed matchweek, so they measure the
    model rather than user behaviour. Each run replaces the previous one.
    """
    __tablename__ = "backtests"
    id = Column(Integer, primary_key=True, index=True)
    fixture_id = Column(Integer, index=True)   # match_results.id this row scored
    season = Column(Text, index=True)
    matchweek = Column(Integer)
    date = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    predicted_home = Column(Integer)
    predicted_away = Column(Integer)
    actual_home = Column(Integer)
    actual_away = Column(Integer)
    home_win_prob = Column(Real)
    draw_prob = Column(Real)
    away_win_prob = Column(Real)
    confidence = Column(Real)
    run_at = Column(Text)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_db():
    """Add new columns to existing tables without dropping data."""
    new_cols = [
        ("match_results", "home_shots", "INTEGER"),
        ("match_results", "away_shots", "INTEGER"),
        ("match_results", "home_corners", "INTEGER"),
        ("match_results", "away_corners", "INTEGER"),
        ("match_results", "home_fouls", "INTEGER"),
        ("match_results", "away_fouls", "INTEGER"),
        ("match_results", "home_yellow_cards", "INTEGER"),
        ("match_results", "away_yellow_cards", "INTEGER"),
        ("match_results", "home_red_cards", "INTEGER"),
        ("match_results", "away_red_cards", "INTEGER"),
        ("match_results", "division", "TEXT"),
        ("match_results", "stats_source", "TEXT"),
        ("predictions", "predicted_stats", "TEXT"),
        ("predictions", "updated_at", "TEXT"),
        ("predictions", "times_predicted", "INTEGER"),
    ]
    indexes = [
        ("idx_match_results_date", "match_results", "date"),
        ("idx_match_results_season", "match_results", "season"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # column already exists
        for name, table, col in indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({col})"))
                conn.commit()
            except Exception:
                pass

        _dedupe_predictions(conn)


def _dedupe_predictions(conn):
    """Collapse duplicate predictions, then make duplicates impossible.

    A fixture used to gain a new row every time it was predicted, so History
    listed the same match repeatedly — "Arsenal vs Chelsea" appeared twice in the
    live database from ordinary use.

    The newest row per (season, fixture) is kept because it reflects the current
    model and the most recent data; the older ones are the superseded answers. Any
    settled result on a discarded row is carried onto the survivor first, so a
    match whose score had already been filled in does not revert to pending.

    The UNIQUE index is the point of the exercise: after this, a duplicate is
    rejected by the database rather than prevented by remembering to call the
    right function at each write site.
    """
    try:
        rows = conn.execute(text(
            "SELECT COUNT(*) FROM ("
            "  SELECT season, fixture FROM predictions"
            "  GROUP BY season, fixture HAVING COUNT(*) > 1)"
        )).scalar()
        if rows:
            print(f"[migrate] collapsing duplicate predictions in {rows} fixture group(s)")
            # Carry any known result onto the row that will survive.
            conn.execute(text("""
                UPDATE predictions AS p
                   SET actual_home = (SELECT o.actual_home FROM predictions o
                                       WHERE o.season = p.season AND o.fixture = p.fixture
                                         AND o.actual_home IS NOT NULL LIMIT 1),
                       actual_away = (SELECT o.actual_away FROM predictions o
                                       WHERE o.season = p.season AND o.fixture = p.fixture
                                         AND o.actual_away IS NOT NULL LIMIT 1)
                 WHERE p.actual_home IS NULL
                   AND EXISTS (SELECT 1 FROM predictions o
                                WHERE o.season = p.season AND o.fixture = p.fixture
                                  AND o.actual_home IS NOT NULL)
            """))
            conn.execute(text("""
                UPDATE predictions SET times_predicted = (
                    SELECT COUNT(*) FROM predictions o
                     WHERE o.season = predictions.season AND o.fixture = predictions.fixture)
            """))
            deleted = conn.execute(text("""
                DELETE FROM predictions WHERE id NOT IN (
                    SELECT MAX(id) FROM predictions GROUP BY season, fixture)
            """)).rowcount
            conn.commit()
            print(f"[migrate] removed {deleted} superseded prediction row(s)")

        conn.execute(text("UPDATE predictions SET times_predicted = 1 WHERE times_predicted IS NULL"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_fixture "
            "ON predictions(season, fixture)"
        ))
        conn.commit()
    except Exception as exc:
        # A failed de-duplication must not stop the app booting; the upsert path
        # still behaves correctly without the index, it just cannot rely on it.
        print(f"[migrate] prediction de-duplication skipped: {type(exc).__name__}: {exc}")


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_db()
