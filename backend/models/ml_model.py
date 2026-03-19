import numpy as np
import joblib
import os
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error
from scipy.stats import poisson

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "saved_models")
HOME_MODEL_PATH = os.path.join(MODEL_DIR, "home_goals_model.pkl")
AWAY_MODEL_PATH = os.path.join(MODEL_DIR, "away_goals_model.pkl")

FEATURE_COLS = [
    "home_avg_gf", "home_avg_ga", "home_avg_xgf", "home_avg_xga",
    "home_avg_sot", "home_avg_poss", "home_form_pts", "home_cs_rate",
    "away_avg_gf", "away_avg_ga", "away_avg_xgf", "away_avg_xga",
    "away_avg_sot", "away_avg_poss", "away_form_pts", "away_cs_rate",
    "home_venue_avg_gf", "home_venue_avg_ga",
    "away_venue_avg_gf", "away_venue_avg_ga",
    "h2h_avg_total_goals", "h2h_home_win_rate",
]


def _make_model():
    return XGBRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )


def train(df):
    os.makedirs(MODEL_DIR, exist_ok=True)
    X = df[FEATURE_COLS].values
    y_home = df["home_goals"].values
    y_away = df["away_goals"].values

    split = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]
    yh_train, yh_val = y_home[:split], y_home[split:]
    ya_train, ya_val = y_away[:split], y_away[split:]

    home_model = _make_model()
    home_model.fit(X_train, yh_train, eval_set=[(X_val, yh_val)], verbose=False)

    away_model = _make_model()
    away_model.fit(X_train, ya_train, eval_set=[(X_val, ya_val)], verbose=False)

    home_mae = mean_absolute_error(yh_val, home_model.predict(X_val))
    away_mae = mean_absolute_error(ya_val, away_model.predict(X_val))
    print(f"Home goals MAE: {home_mae:.3f} | Away goals MAE: {away_mae:.3f}")

    joblib.dump(home_model, HOME_MODEL_PATH)
    joblib.dump(away_model, AWAY_MODEL_PATH)
    return {"home_mae": home_mae, "away_mae": away_mae}


def load_models():
    if not os.path.exists(HOME_MODEL_PATH) or not os.path.exists(AWAY_MODEL_PATH):
        raise FileNotFoundError("Models not trained yet. POST /model/retrain first.")
    return joblib.load(HOME_MODEL_PATH), joblib.load(AWAY_MODEL_PATH)


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
    X = np.array([[feature_dict[c] for c in FEATURE_COLS]])

    home_lambda = max(float(home_model.predict(X)[0]), 0.1)
    away_lambda = max(float(away_model.predict(X)[0]), 0.1)

    pred_home = int(round(home_lambda))
    pred_away = int(round(away_lambda))

    home_win_prob, draw_prob, away_win_prob = _poisson_probs(home_lambda, away_lambda)

    # Confidence: inverse of prediction uncertainty (closer lambdas to integers = higher confidence)
    home_conf = 1 - abs(home_lambda - round(home_lambda))
    away_conf = 1 - abs(away_lambda - round(away_lambda))
    confidence = round((home_conf + away_conf) / 2, 3)

    return {
        "predicted_home": pred_home,
        "predicted_away": pred_away,
        "home_lambda": round(home_lambda, 3),
        "away_lambda": round(away_lambda, 3),
        "home_win_prob": home_win_prob,
        "draw_prob": draw_prob,
        "away_win_prob": away_win_prob,
        "confidence": confidence,
    }


def get_feature_importance() -> dict:
    home_model, away_model = load_models()
    home_imp = dict(zip(FEATURE_COLS, home_model.feature_importances_))
    away_imp = dict(zip(FEATURE_COLS, away_model.feature_importances_))
    top_home = sorted(home_imp.items(), key=lambda x: x[1], reverse=True)[:5]
    top_away = sorted(away_imp.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"home_model_top_features": top_home, "away_model_top_features": top_away}
