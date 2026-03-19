# EPL Score Predictor

An ML-powered agent that predicts English Premier League match scores using historical team performance statistics.

## Stack
- **Backend**: FastAPI + XGBoost + SQLite
- **Frontend**: React + Recharts
- **ML**: XGBoost Regressor (separate models for home/away goals) + Poisson distribution for W/D/L probabilities

---

## Quick Start (Docker)

```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

---

## Local Development

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Start the API (auto-seeds DB on first run)
uvicorn main:app --reload --port 8000
```

### Train the Model

Once the API is running and data is seeded, train the model:

```bash
curl -X POST http://localhost:8000/model/retrain
```

Or via the Swagger UI at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm start
```

Frontend runs at http://localhost:3000

---

## API Endpoints

| Method | Endpoint                  | Description                        |
|--------|---------------------------|------------------------------------|
| GET    | `/health`                 | Health check                       |
| GET    | `/teams`                  | List all EPL teams                 |
| GET    | `/fixtures/recent`        | Recent match results               |
| GET    | `/team/{name}/stats`      | Rolling stats for a team           |
| POST   | `/predict`                | Predict score for a fixture        |
| POST   | `/results`                | Submit actual result post-match    |
| POST   | `/model/retrain`          | Retrain model with latest data     |
| GET    | `/predictions/history`    | All past predictions               |

### Example: Predict a fixture

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"home_team": "Arsenal", "away_team": "Chelsea", "matchweek": 12, "season": "2024-25"}'
```

### Example response

```json
{
  "fixture": "Arsenal vs Chelsea",
  "matchweek": 12,
  "season": "2024-25",
  "predicted_score": "2-1",
  "home_goals": 2,
  "away_goals": 1,
  "probabilities": {
    "home_win": 0.52,
    "draw": 0.24,
    "away_win": 0.24
  },
  "confidence": 0.71,
  "key_drivers": ["home_avg_xgf: 0.312", "away_avg_ga: 0.287", "home_form_pts: 0.201"]
}
```

---

## Run Tests

```bash
cd backend
pytest tests/ -v
```

---

## Data Source

Historical EPL data is automatically downloaded from [football-data.co.uk](https://www.football-data.co.uk) on first startup (seasons 2019-20 through 2023-24).

---

## Project Structure

```
epl-predictor/
├── backend/
│   ├── main.py               # FastAPI app + startup
│   ├── models/ml_model.py    # XGBoost train/predict + Poisson probs
│   ├── data/
│   │   ├── ingestion.py      # Download & seed match data
│   │   └── features.py       # Rolling window feature engineering
│   ├── db/database.py        # SQLAlchemy models + session
│   ├── routers/
│   │   ├── predict.py
│   │   ├── teams.py
│   │   └── results.py
│   ├── tests/test_api.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── components/
│   │       ├── PredictionCard.jsx
│   │       ├── TeamStats.jsx
│   │       └── HistoryTable.jsx
│   └── package.json
├── docker-compose.yml
└── README.md
```
