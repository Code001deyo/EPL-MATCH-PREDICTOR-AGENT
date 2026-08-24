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


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_db()
