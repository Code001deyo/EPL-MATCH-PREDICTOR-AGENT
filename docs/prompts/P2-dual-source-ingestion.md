# P2 — Dual-Source Ingestion

**Agent:** `data-ingestion-engineer`
**Blocks:** P5, P6
**Requires:** P1

## Problem

`db/database.py` defines columns for `home_xg`, `home_shots`, `home_shots_ot`,
`home_possession`, `home_corners`, `home_fouls`, `home_yellow_cards` and their away
equivalents. `seed_database()` writes `None` to every one:

```python
home_xg=None, away_xg=None, home_shots_ot=None, away_shots_ot=None,
home_possession=None, away_possession=None,
```

The PulseLive `/fixtures` endpoint returns goals, gameweek, kickoff and status —
nothing else. So `features.py` invents the rest:

| Feature | Current value |
|---|---|
| `avg_shots` | `avg_gf * 4.5` |
| `avg_corners` | `avg_gf * 2.5` |
| `avg_poss` | `50.0` |
| `avg_fouls` | `11.0` |
| `avg_yellows` | `1.5` |
| `avg_xgf` | falls back to `avg_gf` |

The model is told these are independent statistics. They are constants and copies
of the goals column.

## Task

Add a second ingestion path for real per-match statistics and reconcile it against
the PulseLive fixture spine.

1. Source adapter for football-data.co.uk season CSVs (E0). Fields:
   `HS/AS`, `HST/AST`, `HC/AC`, `HF/AF`, `HY/AY`, `HR/AR`, and closing odds
   `B365H/D/A`. Confirm the real column names against a fetched file before
   building against them.
2. Reconcile on `(date, home_team, away_team)`. The sources disagree on club names
   — build an explicit alias map (Man Utd / Man United, Spurs / Tottenham, Nott'm
   Forest / Nottingham Forest, and others you find). Assert the map in a test.
3. Add red-card columns to the schema; they are available and currently unmodelled.
4. Store per-row provenance so the frontend can report which source produced each
   statistic.
5. PulseLive remains the source of truth for fixtures and live status. Statistics
   are enrichment — a stat-source miss must never drop a fixture.
6. Emit a reconciliation report per season: matched, unmatched, null-stat counts.

## Boundaries

Possession and true xG are in **neither** source. Do not substitute a proxy for
possession — drop it in P5. Do not populate `home_xg` with anything derived from
goals; if a shot-based proxy is wanted it is built and named honestly in P5.

## Acceptance criteria

- Over 95% of historical matches carry real shots, shots on target, corners, fouls
  and cards.
- Unmatched rows are listed per season with their identifying fields — never
  silently defaulted.
- Alias map has test coverage; an unknown club name raises rather than passing
  through as a new team.
- No fixture is lost relative to the PulseLive-only seed. Compare counts before
  and after.

## Verify

```bash
docker compose down -v && docker compose up -d
docker compose logs backend | grep -i "reconcil\|unmatched\|seeded"
curl -s http://localhost:8001/fixtures/recent | head
```
