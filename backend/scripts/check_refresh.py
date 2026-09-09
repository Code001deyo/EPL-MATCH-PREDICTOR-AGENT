"""Decide whether a finished refresh job actually refreshed anything.

This exists because the assertion it replaces lived only inside a YAML `run:`
block, where nothing ran it and nothing tested it. `POST /data/refresh` became a
background job — 202 with a job id, the outcome delivered later via
`/data/jobs/{id}` — and the workflow went on grepping the old synchronous body
for `"status": "refreshed"`. It never found one again, so every scheduled run
failed for eleven days on a refresh that was starting normally.

A job reaching `succeeded` is not the same as a refresh having done its work: the
season may not be published yet, and a future change could return some third
thing. So the job's *result* is checked here, separately from its state.

Reads `job.json` from the working directory. Writes the human summary to
$GITHUB_STEP_SUMMARY and keeps stdout for ::error:: annotations, which GitHub
parses from a step's stdout and would otherwise never see.
"""

from __future__ import annotations

import json
import os
import sys

# The two statuses a healthy refresh can report. "season-not-published" is the
# legitimate pre-season case: the fixtures are not out yet, so there is nothing
# to fetch and saying "refreshed" would be a lie. Anything outside this set is a
# silent failure and must fail the run.
OK_STATUSES = ("refreshed", "season-not-published")


def summarise(job: dict) -> tuple[bool, list[str]]:
    """(ok, markdown lines). Pure, so the test suite can exercise every branch."""
    result = job.get("result") or {}
    status = result.get("status")

    if status not in OK_STATUSES:
        return False, [
            "## Refresh — unexpected status",
            "",
            f"The job finished but reported `{status}`, which is neither a "
            "completed refresh nor the pre-season case.",
            "",
            "```json",
            json.dumps(job, indent=2),
            "```",
        ]

    if status == "season-not-published":
        return True, [
            "## Refresh",
            "",
            f"Season **{result.get('season')}** is not published yet — there were "
            "no fixtures to fetch. This is expected before a season starts.",
        ]

    return True, [
        "## Refresh",
        "",
        f"Season **{result.get('season')}**",
        "",
        "| | |",
        "|---|---|",
        f"| Played fixtures | {result.get('played_fixtures')} |",
        f"| Statistics attached | {result.get('statistics_attached')} |",
        f"| Predictions settled | {result.get('predictions_settled')} |",
        f"| Last refreshed | {result.get('last_refreshed')} |",
    ]


def main() -> int:
    with open("job.json", encoding="utf-8") as fh:
        job = json.load(fh)

    ok, lines = summarise(job)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        # Running locally. Print it, so the script is useful outside CI too.
        print("\n".join(lines))

    if not ok:
        status = (job.get("result") or {}).get("status")
        print(f"::error::unexpected refresh status: {status}")
        return 1

    print(f"refresh status: {(job.get('result') or {}).get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
