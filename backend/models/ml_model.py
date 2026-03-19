import numpy as np
import joblib
import os
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error
from scipy.stats import poisson

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "saved_models")

FEATURE_COLS = [
    "home_avg_gf", "home_avg_ga", "home_avg_xgf", "home_avg_xga",
    "home_avg_sot", "home_avg_shots", "home_avg_poss", "home_avg_corners",
    "home_avg_fouls", "home_avg_yellows", "home_form_pts", "home_cs_rate",
    "home_btts_rate", "home_over_2_5_rate",
    "away_avg_gf", "away_avg_ga", "away_avg_xgf", "away_avg_xga",
    "away_avg_sot", "away_avg_shots", "away_avg_poss", "away_avg_corners",
    "away_avg_fouls", "away_avg_yellows", "away_form_pts", "away_cs_rate",
    "away_btts_rate", "away_over_2_5_rate",
    "home_venue_avg_gf", "home_venue_avg_ga",
    "away_venue_avg_gf", "away_venue_avg_ga",
    "h2h_avg_total_goals", "h2h_home_win_rate",
    "home_dominance_index",
]

# Stat targets beyond goals — trained only when enough non-null data exists
STAT_TARGETS = [
    "home_shots", "away_shots",
    "home_shots_ot", "away_shots_ot",
    "home_possession", "away_possession",
    "home_corners", "away_corners",
    "home_fouls", "away_fouls",
    "home_yellow_cards", "away_yellow_cards",
]

# Heuristic fallbacks when a stat model doesn't exist
STAT_HEURISTICS = {
    "home_shots": lambda h, a: round(h * 4.5 + 6),
    "away_shots": lambda h, a: round(a * 4.5 + 5),
    "home_shots_ot": lambda h, a: round(h * 2.2 + 2),
    "away_shots_ot": lambda h, a: round(a * 2.2 + 1.5),
    "home_possession": lambda h, a: round(50 + (h - a) * 4),
    "away_possession": lambda h, a: round(50 - (h - a) * 4),
    "home_corners": lambda h, a: round(h * 2.5 + 3),
    "away_corners": lambda h, a: round(a * 2.5 + 2.5),
    "home_fouls": lambda h, a: 11,
    "away_fouls": lambda h, a: 12,
    "home_yellow_cards": lambda h, a: 1,
    "away_yellow_cards": lambda h, a: 2,
}

MIN_STAT_SAMPLES = 50


def _model_path(name):
    return os.path.join(MODEL_DIR, f"{name}_model.pkl")


def _make_model():
    return XGBRegressor(
        n_estimators=300, learning_rate=0.05, max_depth=4,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )


def train(df):
    os.makedirs(MODEL_DIR, exist_ok=True)

    # Fill missing feature cols with 0
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0
    df[FEATURE_COLS] = df[FEATURE_COLS].fillna(0.0)

    X = df[FEATURE_COLS].values
    split = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]

    metrics = {}

    # Core goal models
    for target in ["home_goals", "away_goals"]:
        y = df[target].values
        y_train, y_val = y[:split], y[split:]
        model = _make_model()
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        mae = mean_absolute_error(y_val, model.predict(X_val))
        joblib.dump(model, _model_path(target))
        metrics[f"{target}_mae"] = round(mae, 4)
        print(f"{target} MAE: {mae:.3f}")

    # Extended stat models — only train if enough non-null rows
    for target in STAT_TARGETS:
        if target not in df.columns:
            continue
        valid = df[target].dropna()
        if len(valid) < MIN_STAT_SAMPLES:
            print(f"  Skipping {target}: only {len(valid)} non-null rows")
            continue
        y_full = df[target].fillna(df[target].median()).values
        y_train, y_val = y_full[:split], y_full[split:]
        model = _make_model()
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        mae = mean_absolute_error(y_val, model.predict(X_val))
        joblib.dump(model, _model_path(target))
        metrics[f"{target}_mae"] = round(mae, 4)
        print(f"  {target} MAE: {mae:.3f}")

    return metrics


def load_models():
    home_path = _model_path("home_goals")
    away_path = _model_path("away_goals")
    if not os.path.exists(home_path) or not os.path.exists(away_path):
        raise FileNotFoundError("Models not trained yet. POST /model/retrain first.")
    return joblib.load(home_path), joblib.load(away_path)


def _poisson_probs(home_lambda: float, away_lambda: float, max_goals: int = 8):
    home_win, draw, away_win = 0.0, 0.0, 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson.pmf(h, home_lambda) * poisson.pmf(a, away_lambda)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
    total = home_win + draw + away_win
    return round(home_win / total, 3), round(draw / total, 3), round(away_win / total, 3)


def predict(feature_dict: dict) -> dict:
    home_model, away_model = load_models()

    # Fill any missing features with 0
    X = np.array([[feature_dict.get(c, 0.0) for c in FEATURE_COLS]])

    home_lambda = max(float(home_model.predict(X)[0]), 0.1)
    away_lambda = max(float(away_model.predict(X)[0]), 0.1)

    pred_home = int(round(home_lambda))
    pred_away = int(round(away_lambda))

    home_win_prob, draw_prob, away_win_prob = _poisson_probs(home_lambda, away_lambda)

    home_conf = 1 - abs(home_lambda - round(home_lambda))
    away_conf = 1 - abs(away_lambda - round(away_lambda))
    confidence = round((home_conf + away_conf) / 2, 3)

    # Extended stat predictions
    predicted_stats = {}
    for target in STAT_TARGETS:
        path = _model_path(target)
        if os.path.exists(path):
            model = joblib.load(path)
            val = max(float(model.predict(X)[0]), 0.0)
            predicted_stats[target] = int(round(val)) if "possession" not in target else round(val, 1)
        else:
            fn = STAT_HEURISTICS.get(target)
            predicted_stats[target] = fn(home_lambda, away_lambda) if fn else 0

    # Clamp possession so home + away = 100
    if "home_possession" in predicted_stats and "away_possession" in predicted_stats:
        hp = max(min(predicted_stats["home_possession"], 75), 25)
        predicted_stats["home_possession"] = round(hp, 1)
        predicted_stats["away_possession"] = round(100 - hp, 1)

    return {
        "predicted_home": pred_home,
        "predicted_away": pred_away,
        "home_lambda": round(home_lambda, 3),
        "away_lambda": round(away_lambda, 3),
        "home_win_prob": home_win_prob,
        "draw_prob": draw_prob,
        "away_win_prob": away_win_prob,
        "confidence": confidence,
        "predicted_stats": predicted_stats,
    }


def get_feature_importance() -> dict:
    home_model, away_model = load_models()
    home_imp = dict(zip(FEATURE_COLS, home_model.feature_importances_))
    away_imp = dict(zip(FEATURE_COLS, away_model.feature_importances_))
    top_home = sorted(home_imp.items(), key=lambda x: x[1], reverse=True)[:5]
    top_away = sorted(away_imp.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"home_model_top_features": top_home, "away_model_top_features": top_away}
