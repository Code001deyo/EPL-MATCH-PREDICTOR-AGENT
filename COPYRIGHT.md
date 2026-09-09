# Copyright and data attribution

## The software

Copyright © 2026 Hanova Technologies. All rights reserved.

The source code, the trained model, the interface and the written content of this
project are the property of Hanova Technologies. They are published here for
review and are not licensed for reuse, redistribution or commercial use without
written permission.

This is deliberately narrower than the data the project consumes. The two are
different things and conflating them is how a project ends up claiming ownership
of a football league's results, or giving away work it did not mean to.

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

No licence to use them has been granted to this project. They are shown for
identification in a non-commercial context, which is a different position from
being licensed, and the distinction matters if this is ever run commercially:
that would need permission, or the drawn fallback badges in
`frontend/src/components/crest/` used instead. Removing the real crests is one
component change, which is why the fallback was kept rather than deleted.

## Not affiliated

This project is not affiliated with, endorsed by, or connected to the Premier
League, any of its clubs, or football-data.co.uk.

## Not betting advice

Predictions published here are the output of a statistical model, shown with the
record of how often it is right. They are published for interest and are not
advice to place a bet.
