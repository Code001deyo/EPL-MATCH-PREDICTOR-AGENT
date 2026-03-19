from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db.database import init_db, get_db
from data.ingestion import seed_database
from data.features import load_matches, build_training_matrix
from models.ml_model import train
from routers import predict, teams, results, analytics

app = FastAPI(title="EPL Score Predictor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict.router)
app.include_router(teams.router)
app.include_router(results.router)
app.include_router(analytics.router)


@app.on_event("startup")
def startup():
    init_db()
    seed_database()


@app.post("/model/retrain")
def retrain_model(db: Session = Depends(get_db)):
    df = load_matches(db)
    if len(df) < 50:
        return {"error": "Not enough data to train. Need at least 50 matches."}
    print("Building feature matrix...")
    feature_df = build_training_matrix(df)
    print(f"Training on {len(feature_df)} samples...")
    metrics = train(feature_df)
    return {"status": "Model retrained successfully", "metrics": metrics}


@app.get("/health")
def health():
    return {"status": "ok"}
