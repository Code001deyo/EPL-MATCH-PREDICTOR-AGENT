# Security policy

## Reporting a vulnerability

Please report security issues privately, through GitHub's
[private vulnerability reporting](https://github.com/Code001deyo/EPL-MATCH-PREDICTOR-AGENT/security/advisories/new)
on this repository. That opens a draft advisory only the maintainers can see.

Do **not** open a public issue for a vulnerability. A public issue is a
disclosure, and this project runs a live deployment.

You should get an acknowledgement within a few days. Please allow a reasonable
period to fix an issue before disclosing it publicly.

Include what you need to make the problem reproducible: the endpoint or page,
the request, and what happened versus what should have. A proof of concept
helps; please do not include anyone else's data in it.

## What is in scope

- This repository's code, workflows and configuration.
- The deployed site and its API.

Please stay within your own account and your own data while testing. Do not run
denial-of-service tests, do not attempt to access other subscribers' records,
and do not modify or delete data that is not yours. The subscriber table holds
real email addresses.

## What is out of scope

- **The upstream data sources.** Fixtures and results come from the Premier
  League's public endpoints and from football-data.co.uk. Issues in those belong
  to them, not here.
- **Club crests**, which are served from the Premier League's own CDN.
- **Missing hardening with no exploit path**, reported from a scanner without a
  demonstrated impact. It is still welcome as a normal issue; it is not an
  advisory.
- **The model being wrong.** Prediction accuracy is a modelling question and is
  reported openly in the app.

## Things worth knowing before you look

Two of these are deliberate, and reporting them is not necessary:

- **The trained models are published.** `backend/seed/models/` is part of the
  repository by design, so a host with no persistent disk boots working rather
  than untrained. Publishing the model was the point of open sourcing.
- **The API answers anonymously.** Predictions, results and the title race are
  public data and public endpoints. Everything that writes - retrain, backtest,
  simulate, refresh, the subscriber list - requires the admin key or an operator
  session, and the interactive API docs are disabled in production.

What we would very much like to hear about: any path that reads or writes
subscriber records without the admin key, anything that lets a request influence
who an email is addressed to, and any way to get code to run on the deploy host.
