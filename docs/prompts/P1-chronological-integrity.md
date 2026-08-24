# P1 — Chronological Integrity

**Agent:** `data-ingestion-engineer`
**Blocks:** P4, P5, P6 — every rolling window and the train/validation split
**Requires:** P0 (done)

## Problem

Match dates are stored as `DD/MM/YYYY` strings:

```python
# backend/data/ingestion.py:80
date_str = dt.strftime("%d/%m/%Y")
```

Every rolling window filters on string comparison:

```python
# backend/data/features.py:29, 92, 106
home = df[(df["home_team"] == team) & (df["date"] < before_date)]
```

String comparison on `DD/MM/YYYY` sorts by day-of-month first, so
`"05/01/2026" < "31/12/2019"` evaluates `True`. Consequences:

- Every form window, venue split and head-to-head is computed over the wrong matches.
- `load_matches()` orders by this column, so the whole training frame is mis-ordered.
- `train()` splits positionally at `int(len(X) * 0.8)`, so the "validation" set is
  an arbitrary slice of scrambled history.
- The no-leakage requirement is not actually held: "before this date" is not
  reliably before.

## Task

Make chronological order reliable and explicit.

1. Store dates as ISO `YYYY-MM-DD` at ingestion. The kickoff timestamp is already
   parsed as a UTC datetime — format it as ISO instead of `%d/%m/%Y`.
2. Add a proper date column (`Date` type or indexed ISO text) and order every query
   on it explicitly rather than relying on insertion order.
3. Keep a migration path in `db/database.py` consistent with the existing
   lightweight migration helper.
4. One-time wipe and reseed of the `db_data` volume — the stored format changes,
   so existing rows cannot be reinterpreted in place.
5. Audit for any other `strftime`/`strptime` or date string comparison in the
   backend and convert them too.

## Acceptance criteria

- A regression test asserts correct ordering across a year boundary: a fixture on
  05 Jan 2026 sorts after one on 31 Dec 2025.
- A test asserts that for a known fixture, every match in its rolling window has a
  kickoff strictly earlier than that fixture's kickoff.
- Reseed completes and reports per-season counts and max matchweek ≤ 38.
- `pytest tests/ -v` passes.

## Out of scope

Do not add statistics, change the feature set, or retrain. This phase changes only
how time is represented.

## Verify

```bash
docker compose down -v          # wipes db_data — required for this phase
docker compose up -d
docker compose logs -f backend  # watch seed output and per-season validation
cd backend && pytest tests/ -v
```
