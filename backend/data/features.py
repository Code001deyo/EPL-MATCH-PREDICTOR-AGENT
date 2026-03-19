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
        "home_shots": r.home_shots, "away_shots": r.away_shots,
        "home_corners": r.home_corners, "away_corners": r.away_corners,
        "home_fouls": r.home_fouls, "away_fouls": r.away_fouls,
        "home_yellow_cards": r.home_yellow_cards, "away_yellow_cards": r.away_yellow_cards,
    } for r in rows])


def _safe_mean(series, fallback=0.0):
    v = series.dropna()
    return float(v.mean()) if len(v) > 0 else fallback


def _team_rolling(df: pd.DataFrame, team: str, before_date: str, window: int = 5) -> dict:
    home = df[(df["home_team"] == team) & (df["date"] < before_date)].copy()
    away = df[(df["away_team"] == team) & (df["date"] < before_date)].copy()

    home["gf"] = home["home_goals"]
    home["ga"] = home["away_goals"]
    home["xgf"] = home["home_xg"]
    home["xga"] = home["away_xg"]
    home["sot"] = home["home_shots_ot"]
    home["shots"] = home["home_shots"]
    home["poss"] = home["home_possession"]
    home["corners"] = home["home_corners"]
    home["fouls"] = home["home_fouls"]
    home["yellows"] = home["home_yellow_cards"]
    home["pts"] = home.apply(lambda r: 3 if r.home_goals > r.away_goals else (1 if r.home_goals == r.away_goals else 0), axis=1)
    home["cs"] = (home["away_goals"] == 0).astype(int)
    home["btts"] = ((home["home_goals"] > 0) & (home["away_goals"] > 0)).astype(int)
    home["over25"] = ((home["home_goals"] + home["away_goals"]) > 2).astype(int)

    away["gf"] = away["away_goals"]
    away["ga"] = away["home_goals"]
    away["xgf"] = away["away_xg"]
    away["xga"] = away["home_xg"]
    away["sot"] = away["away_shots_ot"]
    away["shots"] = away["away_shots"]
    away["poss"] = away["away_possession"]
    away["corners"] = away["away_corners"]
    away["fouls"] = away["away_fouls"]
    away["yellows"] = away["away_yellow_cards"]
    away["pts"] = away.apply(lambda r: 3 if r.away_goals > r.home_goals else (1 if r.away_goals == r.home_goals else 0), axis=1)
    away["cs"] = (away["home_goals"] == 0).astype(int)
    away["btts"] = ((away["home_goals"] > 0) & (away["away_goals"] > 0)).astype(int)
    away["over25"] = ((away["home_goals"] + away["away_goals"]) > 2).astype(int)

    cols = ["date", "gf", "ga", "xgf", "xga", "sot", "shots", "poss", "corners", "fouls", "yellows", "pts", "cs", "btts", "over25"]
    combined = pd.concat([home[cols], away[cols]]).sort_values("date")

    last5 = combined.tail(window)
    last10 = combined.tail(10)

    if len(last5) == 0:
        return {k: 0.0 for k in ["avg_gf", "avg_ga", "avg_xgf", "avg_xga", "avg_sot", "avg_shots",
                                   "avg_poss", "avg_corners", "avg_fouls", "avg_yellows",
                                   "form_pts", "cs_rate", "btts_rate", "over_2_5_rate"]}

    return {
        "avg_gf": _safe_mean(last5["gf"]),
        "avg_ga": _safe_mean(last5["ga"]),
        "avg_xgf": _safe_mean(last5["xgf"]) if last5["xgf"].notna().any() else _safe_mean(last5["gf"]),
        "avg_xga": _safe_mean(last5["xga"]) if last5["xga"].notna().any() else _safe_mean(last5["ga"]),
        "avg_sot": _safe_mean(last5["sot"]),
        "avg_shots": _safe_mean(last5["shots"], fallback=_safe_mean(last5["gf"]) * 4.5),
        "avg_poss": _safe_mean(last5["poss"], fallback=50.0),
        "avg_corners": _safe_mean(last5["corners"], fallback=_safe_mean(last5["gf"]) * 2.5),
        "avg_fouls": _safe_mean(last5["fouls"], fallback=11.0),
        "avg_yellows": _safe_mean(last5["yellows"], fallback=1.5),
        "form_pts": float(last5["pts"].sum()),
        "cs_rate": _safe_mean(last5["cs"]),
        "btts_rate": _safe_mean(last10["btts"]),
        "over_2_5_rate": _safe_mean(last10["over25"]),
    }


def _venue_split(df: pd.DataFrame, team: str, venue: str, before_date: str, window: int = 5) -> dict:
    if venue == "home":
        matches = df[(df["home_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = _safe_mean(matches["home_goals"]) if len(matches) else 0.0
        ga = _safe_mean(matches["away_goals"]) if len(matches) else 0.0
    else:
        matches = df[(df["away_team"] == team) & (df["date"] < before_date)].tail(window)
        gf = _safe_mean(matches["away_goals"]) if len(matches) else 0.0
        ga = _safe_mean(matches["home_goals"]) if len(matches) else 0.0
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
        "h2h_avg_total_goals": float(total_goals),
        "h2h_home_win_rate": float(home_wins / len(h2h)),
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

    # Composite dominance index
    xgf_h = features["home_avg_xgf"]
    xgf_a = features["away_avg_xgf"]
    features["home_dominance_index"] = (xgf_h - xgf_a) / (xgf_h + xgf_a + 0.01)

    return features


def build_training_matrix(df: pd.DataFrame):
    records = []
    for _, row in df.iterrows():
        feats = build_feature_vector(df, row["home_team"], row["away_team"], row["date"])
        feats["home_goals"] = row["home_goals"]
        feats["away_goals"] = row["away_goals"]
        # Extended stat targets — use NaN if column missing/null
        for col in ["home_shots", "away_shots", "home_shots_ot", "away_shots_ot",
                    "home_possession", "away_possession", "home_corners", "away_corners",
                    "home_fouls", "away_fouls", "home_yellow_cards", "away_yellow_cards"]:
            feats[col] = row.get(col, np.nan)
        records.append(feats)
    return pd.DataFrame(records)
