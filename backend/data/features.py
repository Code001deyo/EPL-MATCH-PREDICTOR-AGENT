import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from db.database import MatchResult


def load_matches(db: Session) -> pd.DataFrame:
    rows = db.query(MatchResult).order_by(MatchResult.date).all()
    return pd.DataFrame([{
        "id": r.id, "season": r.season, "matchweek": r.matchweek,
        "date": r.date, "home_team": r.home_team, "away_team": r.away_team,
        "home_goals": r.home_goals, "away_goals": r.away_goals,
        "home_xg": r.home_xg, "away_xg": r.away_xg,
        "home_shots_ot": r.home_shots_ot, "away_shots_ot": r.away_shots_ot,
        "home_possession": r.home_possession, "away_possession": r.away_possession,
    } for r in rows])


def _team_rolling(df: pd.DataFrame, team: str, before_date: str, window: int = 5) -> dict:
    home = df[(df["home_team"] == team) & (df["date"] < before_date)].copy()
    away = df[(df["away_team"] == team) & (df["date"] < before_date)].copy()

    home["gf"] = home["home_goals"]
    home["ga"] = home["away_goals"]
    home["xgf"] = home["home_xg"]
    home["xga"] = home["away_xg"]
    home["sot"] = home["home_shots_ot"]
    home["poss"] = home["home_possession"]
    home["pts"] = home.apply(lambda r: 3 if r.home_goals > r.away_goals else (1 if r.home_goals == r.away_goals else 0), axis=1)
    home["cs"] = (home["away_goals"] == 0).astype(int)
    home["venue"] = "home"

    away["gf"] = away["away_goals"]
    away["ga"] = away["home_goals"]
    away["xgf"] = away["away_xg"]
    away["xga"] = away["home_xg"]
    away["sot"] = away["away_shots_ot"]
    away["poss"] = away["away_possession"]
    away["pts"] = away.apply(lambda r: 3 if r.away_goals > r.home_goals else (1 if r.away_goals == r.home_goals else 0), axis=1)
    away["cs"] = (away["home_goals"] == 0).astype(int)
    away["venue"] = "away"

    combined = pd.concat([home[["date", "gf", "ga", "xgf", "xga", "sot", "poss", "pts", "cs", "venue"]],
                          away[["date", "gf", "ga", "xgf", "xga", "sot", "poss", "pts", "cs", "venue"]]])
    combined = combined.sort_values("date").tail(window)

    if len(combined) == 0:
        return {k: 0.0 for k in ["avg_gf", "avg_ga", "avg_xgf", "avg_xga", "avg_sot", "avg_poss", "form_pts", "cs_rate"]}

    return {
        "avg_gf": combined["gf"].mean(),
        "avg_ga": combined["ga"].mean(),
        "avg_xgf": combined["xgf"].mean() if combined["xgf"].notna().any() else combined["gf"].mean(),
        "avg_xga": combined["xga"].mean() if combined["xga"].notna().any() else combined["ga"].mean(),
        "avg_sot": combined["sot"].mean() if combined["sot"].notna().any() else 0.0,
        "avg_poss": combined["poss"].mean() if combined["poss"].notna().any() else 50.0,
        "form_pts": combined["pts"].sum(),
        "cs_rate": combined["cs"].mean(),
    }


def _venue_split(df: pd.DataFrame, team: str, venue: str, before_date: str, window: int = 5) -> dict:
    if venue == "home":
        matches = df[(df["home_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = matches["home_goals"].mean() if len(matches) else 0.0
        ga = matches["away_goals"].mean() if len(matches) else 0.0
    else:
        matches = df[(df["away_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = matches["away_goals"].mean() if len(matches) else 0.0
        ga = matches["home_goals"].mean() if len(matches) else 0.0
    return {"venue_avg_gf": gf, "venue_avg_ga": ga}


def _h2h(df: pd.DataFrame, home_team: str, away_team: str, before_date: str, window: int = 5) -> dict:
    h2h = df[
        (((df["home_team"] == home_team) & (df["away_team"] == away_team)) |
         ((df["home_team"] == away_team) & (df["away_team"] == home_team))) &
        (df["date"] < before_date)
    ].tail(window)

    if len(h2h) == 0:
        return {"h2h_avg_total_goals": 2.5, "h2h_home_win_rate": 0.4}

    total_goals = (h2h["home_goals"] + h2h["away_goals"]).mean()
    home_wins = ((h2h["home_team"] == home_team) & (h2h["home_goals"] > h2h["away_goals"])).sum()
    home_wins += ((h2h["away_team"] == home_team) & (h2h["away_goals"] > h2h["home_goals"])).sum()
    return {
        "h2h_avg_total_goals": total_goals,
        "h2h_home_win_rate": home_wins / len(h2h),
    }


def build_feature_vector(df: pd.DataFrame, home_team: str, away_team: str, before_date: str) -> dict:
    home_stats = _team_rolling(df, home_team, before_date)
    away_stats = _team_rolling(df, away_team, before_date)
    home_venue = _venue_split(df, home_team, "home", before_date)
    away_venue = _venue_split(df, away_team, "away", before_date)
    h2h = _h2h(df, home_team, away_team, before_date)

    features = {}
    for k, v in home_stats.items():
        features[f"home_{k}"] = v
    for k, v in away_stats.items():
        features[f"away_{k}"] = v
    features["home_venue_avg_gf"] = home_venue["venue_avg_gf"]
    features["home_venue_avg_ga"] = home_venue["venue_avg_ga"]
    features["away_venue_avg_gf"] = away_venue["venue_avg_gf"]
    features["away_venue_avg_ga"] = away_venue["venue_avg_ga"]
    features["h2h_avg_total_goals"] = h2h["h2h_avg_total_goals"]
    features["h2h_home_win_rate"] = h2h["h2h_home_win_rate"]
    return features


def build_training_matrix(df: pd.DataFrame):
    records = []
    for _, row in df.iterrows():
        feats = build_feature_vector(df, row["home_team"], row["away_team"], row["date"])
        feats["home_goals"] = row["home_goals"]
        feats["away_goals"] = row["away_goals"]
        records.append(feats)
    return pd.DataFrame(records).dropna()
