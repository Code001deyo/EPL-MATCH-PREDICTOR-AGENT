"""What a subscriber actually receives.

Two messages per fixture: the prediction before kickoff, and the result with how
the call went afterwards.

The tone rule for everything in here is the one the rest of the project already
follows — say what the model said and what happened, and do not dress up either.
A model that is right about 53% of 1X2 calls must not send mail that reads like a
tip service. The post-match email therefore reports a wrong call as plainly as a
right one; hiding the misses would make the running record meaningless and is the
single fastest way to lose a reader's trust.
"""

from __future__ import annotations

# Probability is reported to whole percentages. The model does not distinguish
# 52.3% from 52.7% in any meaningful way, and rendering a decimal implies a
# precision the backtest does not support.
def _pct(p) -> str:
    return "—" if p is None else f"{round(float(p) * 100)}%"


def _outcome_line(home: str, away: str, pred: dict) -> str:
    return (
        f"{home} win {_pct(pred.get('home_win_prob'))}   "
        f"Draw {_pct(pred.get('draw_prob'))}   "
        f"{away} win {_pct(pred.get('away_win_prob'))}"
    )


def pre_match(fixture, pred: dict, unsubscribe_url: str) -> tuple[str, str]:
    """(subject, body) for the message sent before kickoff."""
    home, away = fixture.home_team, fixture.away_team
    subject = f"{home} v {away} — the model's call"

    scoreline = f"{pred.get('predicted_home')}-{pred.get('predicted_away')}"
    kickoff = fixture.kickoff_label or fixture.kickoff_utc or "time to be confirmed"

    body = f"""{home} v {away}
Matchweek {fixture.matchweek} · {kickoff}

  Predicted scoreline   {scoreline}
  {_outcome_line(home, away, pred)}

The scoreline is the single most likely result, not a forecast of the exact
score — most matches land on some other scoreline, and the percentages above are
the honest version of the same prediction.

You will get the result and how this call went once the match finishes.

—
Stop these emails: {unsubscribe_url}
"""
    return subject, body


def post_match(fixture, pred: dict | None, home_goals: int, away_goals: int,
               unsubscribe_url: str) -> tuple[str, str]:
    """(subject, body) for the message sent after the final whistle."""
    home, away = fixture.home_team, fixture.away_team
    actual = f"{home_goals}-{away_goals}"
    subject = f"{home} {home_goals}-{away_goals} {away}"

    if not pred:
        # No stored prediction: say so rather than reconstructing one after the
        # fact. A prediction produced once the result is known is not a
        # prediction, and printing it next to the score would imply it was.
        return subject, f"""{home} {actual} {away}
Matchweek {fixture.matchweek}

No prediction was recorded for this fixture, so there is nothing to score it
against.

—
Stop these emails: {unsubscribe_url}
"""

    predicted = f"{pred.get('predicted_home')}-{pred.get('predicted_away')}"

    def result_of(h, a):
        return "home" if h > a else ("away" if a > h else "draw")

    called = result_of(pred.get("predicted_home", 0), pred.get("predicted_away", 0))
    happened = result_of(home_goals, away_goals)

    if predicted == actual:
        verdict = "Called the scoreline exactly."
    elif called == happened:
        verdict = "Called the result correctly; the scoreline was wrong."
    else:
        verdict = "Called it wrong."

    body = f"""{home} {actual} {away}
Matchweek {fixture.matchweek}

  Predicted   {predicted}
  Actual      {actual}

  {verdict}

  What was said beforehand:
  {_outcome_line(home, away, pred)}

One match says very little either way. The model's record over every completed
matchweek is on the site, which is the number worth judging it by.

—
Stop these emails: {unsubscribe_url}
"""
    return subject, body


def confirm_subscription(confirm_url: str) -> tuple[str, str]:
    """(subject, body) for the double opt-in email."""
    return (
        "Confirm your EPL Predictor notifications",
        f"""Someone — probably you — asked for match predictions to be sent to this
address.

Confirm to start receiving them:

{confirm_url}

You will get two emails per match you follow: the prediction shortly before
kickoff, and the result with how the call went shortly after the final whistle.

If this was not you, ignore this email. Nothing is sent to an address that has
not confirmed, so no further messages will arrive.
""")
