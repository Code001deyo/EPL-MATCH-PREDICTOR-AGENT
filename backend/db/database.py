from sqlalchemy import create_engine, Column, Integer, Text, event
from sqlalchemy.types import Float as Real
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import text

import os
os.makedirs("/app/data", exist_ok=True)
DATABASE_URL = "sqlite:////app/data/epl.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class MatchResult(Base):
    __tablename__ = "match_results"
    id = Column(Integer, primary_key=True, index=True)
    season = Column(Text)
    matchweek = Column(Integer)
    date = Column(Text)
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
        ("predictions", "predicted_stats", "TEXT"),
    ]
    with engine.connect() as conn:
        for table, col, col_type in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass  # column already exists


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_db()
