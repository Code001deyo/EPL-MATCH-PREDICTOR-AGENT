import numpy as np
import joblib
import os
from sklearn.metrics import mean_absolute_error
from scipy.stats import poisson

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "saved_models")

FEATURE_COLS = [
    # Rolling form. "xg" features removed — they fell back to goals, so the model
    # was shown the goals column twice. Possession removed — no source publishes it.
    "home_avg_gf", "home_avg_ga", "home_shot_accuracy",
    "home_avg_sot", "home_avg_shots", "home_avg_corners",
    "home_avg_fouls", "home_avg_yellows", "home_form_pts", "home_cs_rate",
    "home_btts_rate", "home_over_2_5_rate",
    "away_avg_gf", "away_avg_ga", "away_shot_accuracy",
    "away_avg_sot", "away_avg_shots", "away_avg_corners",
    "away_avg_fouls", "away_avg_yellows", "away_form_pts", "away_cs_rate",
    "away_btts_rate", "away_over_2_5_rate",
    "home_venue_avg_gf", "home_venue_avg_ga",
    "away_venue_avg_gf", "away_venue_avg_ga",
    "h2h_avg_total_goals", "h2h_home_win_rate",
    "home_dominance_index",
    # Data sufficiency — lets the model discount thin evidence instead of
    # treating a promoted club's calibrated estimate as observed history.
    "home_top_flight_matches", "away_top_flight_matches",
    "home_is_newly_promoted", "away_is_newly_promoted",
    "home_matches_played", "away_matches_played",
    "home_rest_days", "away_rest_days",
    # P9 — opponent-adjusted strength. Everything above describes what a club
    # did; these describe how good it is relative to who it played.
    "home_attack", "home_defence", "home_elo",
    "away_attack", "away_defence", "away_elo",
    "elo_diff", "strength_expected_home_goals", "strength_expected_away_goals",
    "strength_expected_supremacy",
    "home_adj_avg_gf", "away_adj_avg_gf", "home_adj_avg_ga", "away_adj_avg_ga",
    "home_matches_last_14", "away_matches_last_14",
]

# Stat targets beyond goals. Possession is absent from both sources and is no
# longer predicted — an unavailable statistic is reported as unavailable.
STAT_TARGETS = [
    "home_shots", "away_shots",
    "home_shots_ot", "away_shots_ot",
    "home_corners", "away_corners",
    "home_fouls", "away_fouls",
    "home_yellow_cards", "away_yellow_cards",
]

MIN_STAT_SAMPLES = 50

# A season must have at least this many matches to serve as a validation set.
# A full Premier League season is 380; the in-progress season is far smaller and
# holding it out silently reduced validation to a handful of games.
MIN_HOLDOUT_MATCHES = 200


def _model_path(name):
    return os.path.join(MODEL_DIR, f"{name}_model.pkl")


def _make_model():
    # Estimator choice lives in models/backend.py: XGBoost when its wheel is
    # installed, scikit-learn's HistGradientBoosting otherwise. Both split on NaN
    # natively, which is the property the feature layer is built around.
    from models.backend import make_model
    return make_model()


def _season_split_index(df) -> int:
    """Split on a season boundary rather than a fixed 80% of rows.

    The old `int(len(X) * 0.8)` assumed row order was chronological — before P1
    it was not — and cut mid-season, so the validation set shared a season (and
    therefore team form) with training. Holding out whole seasons is the only
    split that mirrors predicting a season the model has never seen.
    """
    if "season" not in df.columns or df["season"].isna().all():
        return int(len(df) * 0.8)

    seasons = sorted(s for s in df["season"].dropna().unique())
    if len(seasons) < 2:
        return int(len(df) * 0.8)

    # The newest season is the one in progress. Holding *that* out gave a
    # validation set of nine matches — enough to make every metric noise and to
    # skip every statistic model for having no validation rows at all. The
    # holdout must be the most recent season that actually finished.
    counts = df["season"].value_counts()
    complete = [s for s in seasons if counts.get(s, 0) >= MIN_HOLDOUT_MATCHES]
    if not complete:
        return int(len(df) * 0.8)

    holdout = complete[-1]
    # Everything before the holdout trains; the holdout and anything after it
    # (the in-progress season) is scored. Rows are date-ordered by load_matches.
    index = int((df["season"] < holdout).sum())
    if index < len(df) * 0.4 or index >= len(df):
        return int(len(df) * 0.8)
    return index


def train(df, on_progress=None):
    """Fit every target model and record honest metrics.

    `on_progress(stage, done, total)` is optional and lets a background job
    report which of the 12 estimators it is on. Progress used to exist only as
    print() to the container's stdout, which the caller could never see.
    """
    from models.backend import backend_description, clean_matrix, fit, feature_importances

    total_targets = 2 + len(STAT_TARGETS)
    done_targets = 0

    def _tick(stage):
        if on_progress:
            on_progress(stage, done_targets, total_targets)

    _tick("preparing feature matrix")

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Missing stays missing. Both backends learn a split direction for NaN;
    # filling with 0.0 told the model "no shots taken" wherever data was absent.
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = np.nan

    X = clean_matrix(df[FEATURE_COLS].values)
    split = _season_split_index(df)
    X_train, X_val = X[:split], X[split:]

    metrics = {"estimator": backend_description()}
    importances = {}

    # Core goal models
    for target in ["home_goals", "away_goals"]:
        y = df[target].values.astype(float)
        y_train, y_val = y[:split], y[split:]
        model = fit(_make_model(), X_train, y_train, X_val, y_val)
        mae = mean_absolute_error(y_val, model.predict(X_val))
        joblib.dump(model, _model_path(target))
        metrics[f"{target}_mae"] = round(mae, 4)
        # Computed once here, at training time, and cached to disk. It used to be
        # recomputed inside every /predict call, which is affordable for XGBoost's
        # native split counts but not for permutation importance.
        importances[target] = feature_importances(model, FEATURE_COLS, X_val, y_val)
        print(f"{target} MAE: {mae:.3f}")
        done_targets += 1
        _tick(f"trained {target}")

    # Extended stat models — shots, shots on target, corners, fouls and cards.
    # These are what make the output a match forecast rather than a scoreline,
    # and they only became trainable once P2 filled the statistics columns.
    stat_coverage = {}
    for target in STAT_TARGETS:
        if target not in df.columns:
            continue
        valid = df[target].dropna()
        stat_coverage[target] = int(len(valid))
        if len(valid) < MIN_STAT_SAMPLES:
            print(f"  Skipping {target}: only {len(valid)} non-null rows")
            done_targets += 1
            _tick(f"skipped {target} (insufficient data)")
            continue
        # Rows without the statistic are dropped rather than median-filled: a
        # median is a fabricated observation, and training on it teaches the
        # model that the league average is what happens when data is missing.
        mask = df[target].notna().values
        y_full = df[target].values.astype(float)
        tr = mask[:split]
        va = mask[split:]
        if tr.sum() < MIN_STAT_SAMPLES or va.sum() == 0:
            print(f"  Skipping {target}: {int(tr.sum())} train / {int(va.sum())} val rows")
            done_targets += 1
            _tick(f"skipped {target} (insufficient data)")
            continue
        model = fit(
            _make_model(),
            X_train[tr], y_full[:split][tr],
            X_val[va], y_full[split:][va],
        )
        mae = mean_absolute_error(y_full[split:][va], model.predict(X_val[va]))
        joblib.dump(model, _model_path(target))
        metrics[f"{target}_mae"] = round(mae, 4)
        print(f"  {target} MAE: {mae:.3f}  ({int(tr.sum())} train rows)")
        done_targets += 1
        _tick(f"trained {target}")

    metrics["stat_coverage"] = stat_coverage
    _tick("computing baselines")
    _save_importances(importances)

    # Baselines. Recorded every run so an improvement always has something to be
    # measured against — a model that cannot beat Poisson on goal averages has
    # not earned its complexity, and that must be visible rather than inferred.
    metrics["baselines"] = _baselines(df, split)
    metrics["validation"] = {
        "split": "season-holdout" if "season" in df.columns else "positional",
        "train_rows": int(split),
        "val_rows": int(len(df) - split),
        "features": len(FEATURE_COLS),
    }
    # Every baseline gets a verdict, including the ones the model loses to. The
    # median was previously computed but left out of the flags, so metrics.json
    # read as a clean sweep while the median in fact beat the model on away goals.
    for target in ["home_goals", "away_goals"]:
        model_mae = metrics.get(f"{target}_mae")
        if model_mae is None:
            continue
        losses = []
        for name in ["poisson", "median", "constant", "form"]:
            base_mae = metrics["baselines"].get(f"{target}_{name}_mae")
            if base_mae is None:
                continue
            beat = model_mae < base_mae
            metrics["baselines"][f"{target}_beats_{name}"] = bool(beat)
            if not beat:
                losses.append(name)
            print(f"  {target}: model {model_mae:.3f} vs {name} {base_mae:.3f} "
                  f"-> {'model wins' if beat else 'BASELINE WINS'}")
        # Surfaced as its own field so the dashboard cannot show a green tick
        # without also showing what the model failed to beat.
        metrics["baselines"][f"{target}_lost_to"] = losses

    # Outcome accuracy on the same holdout. MAE answers "how far off were the
    # goal counts"; this answers the question actually being asked of a match
    # predictor — how often does it call the right result.
    _tick("scoring holdout accuracy")
    metrics["accuracy"] = _outcome_accuracy(df, X, split)

    _save_metrics(metrics)
    _tick("complete")
    return metrics


def _outcome_accuracy(df, X, split: int) -> dict:
    """W/D/L and exact-score accuracy over the held-out season."""
    home_model, away_model = load_models()
    X_val = X[split:]
    if len(X_val) == 0:
        return {}

    pred_h = np.maximum(home_model.predict(X_val), 0.0)
    pred_a = np.maximum(away_model.predict(X_val), 0.0)
    act_h = df["home_goals"].values[split:].astype(float)
    act_a = df["away_goals"].values[split:].astype(float)

    rh, ra = np.rint(pred_h), np.rint(pred_a)
    exact = float(np.mean((rh == act_h) & (ra == act_a)))

    def outcome(h, a):
        return np.where(h > a, 1, np.where(h == a, 0, -1))

    # The rounded scoreline is a poor outcome classifier — two near-identical
    # lambdas both round to the same integer and read as a draw. The W/D/L call
    # comes from the Poisson distribution over the raw rates, which is what the
    # API returns to users, so this measures what they actually see.
    called = np.array([
        _argmax_outcome(*_poisson_probs(float(h), float(a)))
        for h, a in zip(np.maximum(pred_h, 0.1), np.maximum(pred_a, 0.1))
    ])
    truth = outcome(act_h, act_a)
    correct_result = float(np.mean(called == truth))

    # Always-home-win is the baseline any football model must clear; the home
    # side wins roughly 45% of Premier League matches for free.
    home_rate = float(np.mean(truth == 1))

    # Log loss over the three-way probabilities. Accuracy only records whether
    # the top pick was right; log loss records whether the *confidence* was
    # earned, which is what a probability output is claiming. The reference is
    # the training-set base rate — a model that cannot beat "the league splits
    # 45/25/30 every week" has added nothing.
    probs = np.array([
        _poisson_probs(float(h), float(a))
        for h, a in zip(np.maximum(pred_h, 0.1), np.maximum(pred_a, 0.1))
    ])
    truth_idx = np.where(truth == 1, 0, np.where(truth == 0, 1, 2))
    eps = 1e-9
    model_ll = float(-np.mean(np.log(np.clip(probs[np.arange(len(truth)), truth_idx], eps, 1))))

    train_truth = outcome(
        df["home_goals"].values[:split].astype(float),
        df["away_goals"].values[:split].astype(float),
    )
    base = np.array([
        float(np.mean(train_truth == 1)),
        float(np.mean(train_truth == 0)),
        float(np.mean(train_truth == -1)),
    ])
    base_ll = float(-np.mean(np.log(np.clip(base[truth_idx], eps, 1))))

    return {
        "holdout_season": _holdout_season(df, split),
        "matches_scored": int(len(X_val)),
        "correct_result_pct": round(correct_result * 100, 1),
        "exact_score_pct": round(exact * 100, 1),
        "always_home_pct": round(home_rate * 100, 1),
        "beats_always_home": bool(correct_result > home_rate),
        "log_loss": round(model_ll, 4),
        "base_rate_log_loss": round(base_ll, 4),
        "beats_base_rate": bool(model_ll < base_ll),
    }


def _argmax_outcome(home_p, draw_p, away_p) -> int:
    best = max(home_p, draw_p, away_p)
    if best == home_p:
        return 1
    return 0 if best == draw_p else -1


def _holdout_season(df, split: int):
    if "season" not in df.columns:
        return None
    tail = df["season"].values[split:]
    return str(tail[0]) if len(tail) else None


# A club needs this many training matches before its strength rate is trusted.
MIN_BASELINE_MATCHES = 10


def _baselines(df, split: int) -> dict:
    """Naive baselines on the same holdout the model is scored on."""
    out = {}
    for target in ["home_goals", "away_goals"]:
        if target not in df.columns:
            continue
        y = df[target].values
        y_train, y_val = y[:split], y[split:]
        if len(y_val) == 0 or len(y_train) == 0:
            continue

        # Constant baseline: always predict the training-set mean.
        mean_pred = np.full(len(y_val), float(np.nanmean(y_train)))
        out[f"{target}_constant_mae"] = round(float(mean_absolute_error(y_val, mean_pred)), 4)

        # Median baseline, stated explicitly because it is the one that makes MAE
        # comparisons honest: MAE is minimised by the median, and for Premier
        # League goals the median is the integer 1. Any real-valued model will
        # tend to lose to it on MAE while being a better rate estimator, so MAE
        # alone must not be read as the verdict on the model.
        median_pred = np.full(len(y_val), float(np.nanmedian(y_train)))
        out[f"{target}_median_mae"] = round(float(mean_absolute_error(y_val, median_pred)), 4)

        # NOTE: a single-rate Poisson has the training mean as its MLE, so its
        # point prediction is identical to the constant baseline. This file used
        # to record exactly that and call it "the Poisson baseline", which made
        # `beats_poisson` mean nothing more than "beats the training mean" — a
        # baseline no model can fail. The real benchmark is the team-strength
        # Poisson added in _poisson_strength_baseline below.

    # Rolling-form baseline: use each side's own recent scoring rate directly.
    for target, feature in [("home_goals", "home_avg_gf"), ("away_goals", "away_avg_gf")]:
        if target not in df.columns or feature not in df.columns:
            continue
        y_val = df[target].values[split:]
        form = df[feature].values[split:]
        mask = ~np.isnan(form.astype(float))
        if mask.sum() == 0:
            continue
        out[f"{target}_form_mae"] = round(
            float(mean_absolute_error(y_val[mask], form.astype(float)[mask])), 4
        )

    out.update(_poisson_strength_baseline(df, split))
    return out


def _poisson_strength_baseline(df, split: int) -> dict:
    """Classic football benchmark: team attack/defence rates with home advantage.

    This is the baseline that can actually embarrass the model. Rates are fitted
    on the training rows only — a team's strength must not be estimated using
    the holdout matches it is then scored on.

        lambda_home = league_home_rate * attack(home) * defence(away)
        lambda_away = league_away_rate * attack(away) * defence(home)

    A model carrying 55 engineered features that cannot beat this has not earned
    its complexity, so the comparison is recorded on every run.
    """
    needed = {"home_team", "away_team", "home_goals", "away_goals"}
    if not needed.issubset(df.columns) or split <= 0 or split >= len(df):
        return {}

    train_df = df.iloc[:split]
    val_df = df.iloc[split:]

    league_home = float(np.nanmean(train_df["home_goals"].values.astype(float)))
    league_away = float(np.nanmean(train_df["away_goals"].values.astype(float)))
    if not np.isfinite(league_home) or not np.isfinite(league_away):
        return {}

    scored, conceded, played = {}, {}, {}
    for row in train_df.itertuples():
        for team, gf, ga in (
            (row.home_team, row.home_goals, row.away_goals),
            (row.away_team, row.away_goals, row.home_goals),
        ):
            if gf is None or ga is None:
                continue
            scored[team] = scored.get(team, 0.0) + float(gf)
            conceded[team] = conceded.get(team, 0.0) + float(ga)
            played[team] = played.get(team, 0) + 1

    league_per_team = (league_home + league_away) / 2.0

    def _rate(table, team):
        """Strength relative to the league. Unseen teams get 1.0 (league average),
        which is an explicit 'no information' choice, not a fabricated stat."""
        n = played.get(team, 0)
        if n < MIN_BASELINE_MATCHES or league_per_team <= 0:
            return 1.0
        return (table.get(team, 0.0) / n) / league_per_team

    lam_h, lam_a, act_h, act_a = [], [], [], []
    for row in val_df.itertuples():
        lam_h.append(league_home * _rate(scored, row.home_team) * _rate(conceded, row.away_team))
        lam_a.append(league_away * _rate(scored, row.away_team) * _rate(conceded, row.home_team))
        act_h.append(float(row.home_goals))
        act_a.append(float(row.away_goals))

    if not lam_h:
        return {}

    lam_h, lam_a = np.array(lam_h), np.array(lam_a)
    act_h, act_a = np.array(act_h), np.array(act_a)

    out = {
        "home_goals_poisson_mae": round(float(mean_absolute_error(act_h, lam_h)), 4),
        "away_goals_poisson_mae": round(float(mean_absolute_error(act_a, lam_a)), 4),
        "poisson_baseline": "team-strength (attack x defence x home advantage)",
    }

    # Score the same baseline on the question the app actually answers.
    correct, lls = 0, []
    for i in range(len(lam_h)):
        h, d, a = _poisson_probs(float(lam_h[i]), float(lam_a[i]))
        pred = _argmax_outcome(h, d, a)
        actual = 1 if act_h[i] > act_a[i] else (0 if act_h[i] == act_a[i] else -1)
        correct += int(pred == actual)
        p = {1: h, 0: d, -1: a}[actual]
        lls.append(-np.log(max(p, 1e-12)))
    out["poisson_correct_result_pct"] = round(correct / len(lam_h) * 100, 1)
    out["poisson_log_loss"] = round(float(np.mean(lls)), 4)
    return out


def _save_metrics(metrics: dict) -> None:
    import json
    from datetime import datetime, timezone
    payload = dict(metrics)
    payload["trained_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as fh:
        json.dump(payload, fh, indent=2)


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


def _confidence(home_lambda: float, away_lambda: float, feature_dict: dict) -> float:
    """Confidence combining outcome decisiveness with evidence sufficiency.

    Two independent things make a prediction trustworthy: the model separating
    the outcomes clearly, and there being enough real history behind the inputs.
    A confident-looking scoreline built on a calibrated Championship prior is not
    the same claim as one built on five seasons of Premier League matches.
    """
    from data.calibration import calibration_confidence_penalty

    # 1. Decisiveness: how far the most likely outcome stands above the others.
    home_p, draw_p, away_p = _poisson_probs(home_lambda, away_lambda)
    ordered = sorted([home_p, draw_p, away_p], reverse=True)
    decisiveness = ordered[0] - ordered[1]          # 0.0 (toss-up) .. 1.0 (certain)

    # 2. Evidence: how much of the feature vector is actually populated.
    tracked = [feature_dict.get(c) for c in FEATURE_COLS]
    present = sum(
        1 for v in tracked
        if v is not None and not (isinstance(v, float) and np.isnan(v))
    )
    coverage = present / len(FEATURE_COLS) if FEATURE_COLS else 0.0

    # 3. Penalty for resting on cross-division calibration rather than observation.
    home_matches = feature_dict.get("home_top_flight_matches") or 0
    away_matches = feature_dict.get("away_top_flight_matches") or 0
    penalty = max(
        calibration_confidence_penalty(home_matches, bool(feature_dict.get("home_is_newly_promoted"))),
        calibration_confidence_penalty(away_matches, bool(feature_dict.get("away_is_newly_promoted"))),
    )

    raw = (0.6 * decisiveness + 0.4 * coverage) * (1.0 - min(penalty, 0.9))
    return round(max(0.0, min(1.0, raw)), 3)


def predict(feature_dict: dict) -> dict:
    home_model, away_model = load_models()

    # Missing stays missing here too. Substituting 0.0 at prediction time after
    # training on NaN sends the model down the wrong split — 0.0 means "took no
    # shots", which is a measurement, not an absence.
    X = np.array([[_as_float(feature_dict.get(c)) for c in FEATURE_COLS]], dtype=float)

    home_lambda = max(float(home_model.predict(X)[0]), 0.1)
    away_lambda = max(float(away_model.predict(X)[0]), 0.1)

    pred_home = int(round(home_lambda))
    pred_away = int(round(away_lambda))

    home_win_prob, draw_prob, away_win_prob = _poisson_probs(home_lambda, away_lambda)

    # Confidence from the predictive distribution and the evidence behind it.
    # The old score was `1 - abs(lambda - round(lambda))` — the distance to the
    # nearest integer, which measures rounding, not certainty: a prediction of
    # exactly 2.0 scored maximum confidence whether it rested on five seasons of
    # history or on a promoted club with none.
    confidence = _confidence(home_lambda, away_lambda, feature_dict)

    # Extended stat predictions
    predicted_stats = {}
    for target in STAT_TARGETS:
        path = _model_path(target)
        if os.path.exists(path):
            model = joblib.load(path)
            val = max(float(model.predict(X)[0]), 0.0)
            predicted_stats[target] = int(round(val))
        else:
            # No trained model for this statistic means we cannot predict it.
            # The old heuristics returned invented numbers (fouls = 11) that were
            # indistinguishable from real predictions in the UI.
            predicted_stats[target] = None

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


def _as_float(value):
    """None and non-numeric become NaN, not zero."""
    if value is None:
        return np.nan
    if isinstance(value, bool):
        return float(value)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out


def _importance_path():
    return os.path.join(MODEL_DIR, "importances.json")


def _save_importances(importances: dict) -> None:
    import json
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(_importance_path(), "w") as fh:
        json.dump(importances, fh, indent=2)


def get_feature_importance() -> dict:
    """Top drivers, read from the cache written at training time.

    Not recomputed per request: with the sklearn backend importance is measured
    by permutation, which would put a few hundred extra model evaluations inside
    every /predict call.
    """
    import json
    path = _importance_path()
    if not os.path.exists(path):
        raise FileNotFoundError("Importances not available. POST /model/retrain first.")
    with open(path) as fh:
        data = json.load(fh)

    def top(key):
        items = data.get(key, {})
        return sorted(items.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]

    return {
        "home_model_top_features": top("home_goals"),
        "away_model_top_features": top("away_goals"),
    }
