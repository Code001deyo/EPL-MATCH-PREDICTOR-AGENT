# EPL Predictor — Defect Correction Prompt

## Context
You are maintaining an EPL score prediction agent backed by historical match data from
football-data.co.uk (seasons 2019-20 through 2025-26). The agent uses FastAPI + XGBoost
and stores data in SQLite via SQLAlchemy.

---

## Confirmed Defects

### Defect 1 — Matchweek Assignment Is Wrong
**Root cause:** The CSV from football-data.co.uk has NO `Matchweek` column. The current
`assign_matchweek()` function in `data/ingestion.py` uses a sequential team-game-count
algorithm that produces incorrect results:
- 2019-20 season: 69 matchweeks instead of 38
- 2025-26 season: 53 matchweeks instead of 38 (or fewer if season is in progress)
- Fixtures per matchweek are uneven (e.g. MW1: 9, MW22: 8) instead of always 10

**EPL rule:** Each matchweek has exactly 10 fixtures (20 teams, each plays once).
All fixtures within the same calendar date-block (typically Fri–Mon) belong to the
same gameweek.

**Fix required:** Replace `assign_matchweek()` with a date-clustering approach:
1. Sort all matches by date
2. Group matches into rounds by clustering consecutive dates with a max gap of
   3 days between groups (a new gameweek starts when the gap between match dates
   exceeds 3 days)
3. Number the groups 1..N — these are the true matchweeks
4. Validate: each matchweek should have ≤ 10 fixtures (some rounds are split across
   midweek/weekend due to cup competitions — accept 1–10 fixtures per round)

### Defect 2 — Database Contains Stale Wrong Matchweek Data
**Root cause:** The DB was seeded with the broken matchweek values. Simply fixing the
code is not enough — the existing records must be wiped and re-seeded.

**Fix required:**
1. On startup, detect if matchweek data is corrupted (max matchweek > 38 for any season)
2. If corrupted, drop and re-seed all match_results
3. After re-seeding, validate: assert max(matchweek) <= 38 for each completed season

### Defect 3 — Fixture Selector Shows Wrong Matchweek Numbers
**Root cause:** The frontend fixture selector groups by matchweek from the DB, which
currently shows MW1–MW53 instead of MW1–MW38.

**Fix required:** Once Defect 1 and 2 are fixed, the fixture selector will automatically
show correct MW1–MW38 groupings. No frontend change needed beyond the backend fix.

### Defect 4 — 2025-26 Season Is Incomplete (In-Progress Season)
**Root cause:** The 2025-26 season CSV only contains played matches (301 as of the
current date). The remaining unplayed fixtures are not in the CSV.

**Fix required:**
- Accept that the current season will have fewer than 380 fixtures until it completes
- The fixture selector should show only played matchweeks for the current season
- Label the current season clearly in the UI as "2025-26 (In Progress)"
- Do NOT attempt to predict fixtures that haven't been played yet via fixture_id
  (those don't exist in the DB). Custom team-vs-team prediction via home_team/away_team
  fields handles future fixtures.

---

## Fix Implementation Plan

### Step 1 — Fix `assign_matchweek()` in `backend/data/ingestion.py`
Replace the broken sequential algorithm with date-gap clustering:

```python
def assign_matchweek(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    df = df.sort_values("Date").reset_index(drop=True)
    unique_dates = sorted(df["Date"].unique())
    
    matchweek = 1
    date_to_mw = {}
    prev_date = None
    for d in unique_dates:
        if prev_date is not None and (d - prev_date).days > 3:
            matchweek += 1
        date_to_mw[d] = matchweek
        prev_date = d
    
    df["matchweek"] = df["Date"].map(date_to_mw)
    df["Date"] = df["Date"].dt.strftime("%d/%m/%Y")
    return df
```

### Step 2 — Add corruption detection + auto-reseed in `seed_database()`
```python
def is_matchweek_corrupted(db) -> bool:
    from sqlalchemy import func
    result = db.query(func.max(MatchResult.matchweek)).scalar()
    return result is not None and result > 38

def seed_database():
    init_db()
    db = SessionLocal()
    if is_matchweek_corrupted(db):
        print("Corrupted matchweek data detected. Wiping and re-seeding...")
        db.query(MatchResult).delete()
        db.commit()
    # ... rest of seed logic unchanged
```

### Step 3 — Validate after seeding
After bulk insert, run:
```python
for season in SEASONS:
    max_mw = db.query(func.max(MatchResult.matchweek)).filter(
        MatchResult.season == season
    ).scalar()
    print(f"{season}: max matchweek = {max_mw}")
    assert max_mw <= 38, f"Season {season} has {max_mw} matchweeks — still broken!"
```

### Step 4 — Update `/seasons` endpoint to flag in-progress season
```python
CURRENT_SEASON = "2025-26"

@router.get("/seasons")
def get_seasons(db):
    rows = db.query(MatchResult.season).distinct().order_by(MatchResult.season).all()
    return {"seasons": [
        {"id": r[0], "label": f"{r[0]} (In Progress)" if r[0] == CURRENT_SEASON else r[0]}
        for r in rows
    ]}
```

### Step 5 — Rebuild Docker image and retrain model
After fixing the code:
```bash
docker-compose down -v
docker rmi epl-predictor-backend -f
docker-compose up -d --build
# Wait for seeding to complete, then:
curl -X POST http://localhost:8001/model/retrain
```

---

## Validation Checklist
After applying fixes, verify:
- [ ] Each season has exactly 380 fixtures (except 2025-26 which is in progress)
- [ ] Max matchweek per completed season = 38
- [ ] Each matchweek has between 1 and 10 fixtures
- [ ] Fixture selector in UI shows MW1–MW38 only
- [ ] Prediction for a fixture_id returns correct fixture metadata
- [ ] Model retrains successfully on clean data

---

## Data Source Reference
- football-data.co.uk CSV columns used: `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `HST`, `AST`
- Date format in CSV: `DD/MM/YYYY`
- No native matchweek column exists — must be derived from dates
- Each EPL season runs August to May
- 20 teams × 38 games each = 380 total fixtures per season
- Each gameweek = 10 simultaneous fixtures
