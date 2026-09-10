# Copyright and data attribution

## The software

Copyright © 2026 Hanova Technologies.

The source code in this repository is licensed under the **Apache License,
Version 2.0**. The full text is in [`LICENSE`](LICENSE); the short version is
that you may use, modify and redistribute it, including commercially, provided
you keep the notice, state your changes, and accept that it comes with no
warranty. Apache-2.0 rather than MIT because it grants an explicit patent
licence and requires changed files to be marked, which suits company-owned code.

The licence covers the code, and nothing else in the repository. In particular
it does not grant any right to:

- **Club crests and Premier League marks.** Not ours to license. See below.
- **Match data.** Not ours either, and not covered by a software licence in
  any case. See below.
- **The Hanova Technologies name and logo.** Trade marks are excluded from
  Apache-2.0 by section 6, which is deliberate: you may fork the code, and you
  may not publish the fork as though Hanova published it.

The trained model files under `backend/seed/models/` are released under the same
licence as the code. They are derived from public match results, not from
anything proprietary.

This separation is the point. Conflating a software licence with the data a
program consumes is how a project ends up claiming ownership of a football
league's results, or giving away work it did not mean to.

## The data

None of the match data is ours, and none of it is claimed.

| Source | What it provides | Terms |
|---|---|---|
| [Premier League](https://www.premierleague.com) (PulseLive feed) | Fixtures, results, schedule, gameweek and live status; club identifiers | Public endpoints, no licence granted for redistribution |
| [football-data.co.uk](https://www.football-data.co.uk) | Per-match statistics: shots, corners, fouls, cards, closing odds | Free for personal use, attribution requested |

Results and statistics are facts about matches that were played. They are
reported here, not owned here.

## Club badges

Club crests are displayed from the Premier League's own content delivery network
and are **not** copied into this repository. They remain the registered trade
marks of the individual clubs and of the Premier League.

No licence to use them has been granted to this project, and the Apache-2.0
licence on the code cannot grant one either - it only covers what Hanova
Technologies owns. They are shown for identification, which is a different
position from being licensed.

This matters directly to anyone taking the code up under that licence: the
crests are the one part of the running site that is not yours to use. The drawn
fallback badges in `frontend/src/components/crest/` are ours and are covered by
the licence, and switching to them is a one-component change. That is why the
fallback was kept rather than deleted.

## Not affiliated

This project is not affiliated with, endorsed by, or connected to the Premier
League, any of its clubs, or football-data.co.uk.

## Not betting advice

Predictions published here are the output of a statistical model, shown with the
record of how often it is right. They are published for interest and are not
advice to place a bet.
