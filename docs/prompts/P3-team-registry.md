# P3 — Team Registry and Continuity

**Agent:** `data-ingestion-engineer`
**Blocks:** P4
**Requires:** P2

## Problem

The system has no concept of a club as a persistent entity. Teams exist only as
name strings on match rows, and league membership is implicit in whichever season
happens to be loaded. Two failures follow:

**Relegated clubs.** Burnley, West Ham and Wolves left the Premier League for
2026-27. Their history must be retained in full — they will return, and their past
matches remain valid evidence about opponents they played.

**Promoted clubs.** Coventry, Hull and Ipswich have no Premier League history at
all. Today `_team_rolling()` returns every feature as `0.0` for them, which the
model reads as a team that neither scores nor concedes.

## Task

Make a club a first-class, permanent entity and give every 2026-27 club a real
history.

1. Team registry table keyed on a canonical club id, carrying the display name and
   the source alias set from P2.
2. Per-season division membership, so a club's record reads correctly across moves
   between divisions.
3. Ingest E1 (Championship) history for promoted clubs via the P2 adapter, tagged
   with its division. Same statistics, same schema, different division label.
4. Guarantee no deletion path removes a relegated club's matches. Check
   `seed_database()`'s corruption-wipe branch and `refresh_current_season()`'s
   delete-then-reinsert — both currently delete by season and must not be able to
   orphan a club's record.
5. Resolve every match row to canonical club ids rather than raw name strings.

## Design note

Division is an attribute of a *match*, not of a club. A club's history is a
sequence of matches each played in some division. This is what lets P4 apply a
translation factor to the Championship rows while leaving Premier League rows
untouched.

## Acceptance criteria

- Every one of the 20 clubs in 2026-27 has a non-empty match history at
  matchweek 1.
- Each historical row is labelled with the division it was played in.
- Burnley, West Ham and Wolves retain complete Premier League history despite not
  appearing in the current season.
- A test asserts that reseeding the current season does not delete any prior-season
  or other-division rows.
- Club name variants across both sources resolve to one canonical id.

## Verify

```bash
curl -s http://localhost:8001/teams | python -m json.tool | head -40
curl -s "http://localhost:8001/team/Coventry/stats"   # must show real E1 history
curl -s "http://localhost:8001/team/Wolves/stats"     # retained after relegation
```
