from sqlalchemy import create_engine, Column, Integer, Text
from sqlalchemy.types import Float as Real
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./epl.db"

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
    created_at = Column(Text)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
