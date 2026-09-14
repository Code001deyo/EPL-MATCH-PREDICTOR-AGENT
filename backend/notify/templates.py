"""What a subscriber actually receives.

Two messages per fixture: the prediction before kickoff, and the result with how
the call went afterwards.

The tone rule for everything in here is the one the rest of the project already
follows - say what the model said and what happened, and do not dress up either.
A model that is right about 53% of 1X2 calls must not send mail that reads like a
tip service. The post-match email therefore reports a wrong call as plainly as a
right one; hiding the misses would make the running record meaningless and is the
single fastest way to lose a reader's trust.

Every message is built twice, as plain text and as HTML, and both are sent. The
HTML version is what nearly every mail client shows, and in it the unsubscribe
and confirm links are buttons: the reader sees "Unsubscribe", not a URL with a
token in it. The token still travels in the message - it has to, it is the
credential that makes one click enough - but it lives in the button's href, not
in front of the reader's eyes. The plain-text version keeps the bare URL because a
text-only client has no button to press and must still have a way out.
"""

from __future__ import annotations

import html as _html
import os

from notify.html_mail import button, render

SIGNATURE = "EPL Score Predictor, a product of Hanova Technologies."


def privacy_url() -> str:
    """Where the privacy policy lives.

    Built from PUBLIC_SITE_URL so it points at whichever instance sent the mail.
    Bulk email that does not say who sent it, how to leave and where the policy
    is reads as spam to a filter and to a person.
    """
    base = (os.environ.get("PUBLIC_SITE_URL") or "").rstrip("/")
    return f"{base}/privacy"


# Probability is reported to whole percentages. The model does not distinguish
# 52.3% from 52.7% in any meaningful way, and rendering a decimal implies a
# precision the backtest does not support.
def _pct(p) -> str:
    return "-" if p is None else f"{round(float(p) * 100)}%"


def _outcome_line(home: str, away: str, pred: dict) -> str:
    return (
        f"{home} win {_pct(pred.get('home_win_prob'))}   "
        f"Draw {_pct(pred.get('draw_prob'))}   "
        f"{away} win {_pct(pred.get('away_win_prob'))}"
    )


def _text_footer(unsubscribe_url: str) -> str:
    return f"""
-
{SIGNATURE}
Unsubscribe: {unsubscribe_url}
Privacy: {privacy_url()}
"""


def _notification(core: str, unsubscribe_url: str) -> tuple[str, str]:
    """(text, html) for a notification whose body is `core`.

    The two share the words. Only the way out differs: a URL in text, a button
    in HTML.
    """
    text = core + _text_footer(unsubscribe_url)
    html = render(
        core,
        actions=button("Unsubscribe", unsubscribe_url, quiet=True),
        footer=(
            f"{_html.escape(SIGNATURE)}<br>"
            f"<a href=\"{_html.escape(privacy_url(), quote=True)}\">Privacy</a>"
        ),
    )
    return text, html


def pre_match(fixture, pred: dict, unsubscribe_url: str) -> tuple[str, str, str]:
    """(subject, text, html) for the message sent before kickoff."""
    home, away = fixture.home_team, fixture.away_team
    subject = f"{home} v {away} - the model's call"

    scoreline = f"{pred.get('predicted_home')}-{pred.get('predicted_away')}"
    kickoff = fixture.kickoff_label or fixture.kickoff_utc or "time to be confirmed"

    core = f"""{home} v {away}
Matchweek {fixture.matchweek} · {kickoff}

  Predicted scoreline   {scoreline}
  {_outcome_line(home, away, pred)}

The scoreline is the single most likely result, not a forecast of the exact
score - most matches land on some other scoreline, and the percentages above are
the honest version of the same prediction.

You will get the result and how this call went once the match finishes.
"""
    text, html = _notification(core, unsubscribe_url)
    return subject, text, html


def post_match(fixture, pred: dict | None, home_goals: int, away_goals: int,
               unsubscribe_url: str) -> tuple[str, str, str]:
    """(subject, text, html) for the message sent after the final whistle."""
    home, away = fixture.home_team, fixture.away_team
    actual = f"{home_goals}-{away_goals}"
    subject = f"{home} {home_goals}-{away_goals} {away}"

    if not pred:
        # No stored prediction: say so rather than reconstructing one after the
        # fact. A prediction produced once the result is known is not a
        # prediction, and printing it next to the score would imply it was.
        core = f"""{home} {actual} {away}
Matchweek {fixture.matchweek}

No prediction was recorded for this fixture, so there is nothing to score it
against.
"""
        text, html = _notification(core, unsubscribe_url)
        return subject, text, html

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

    core = f"""{home} {actual} {away}
Matchweek {fixture.matchweek}

  Predicted   {predicted}
  Actual      {actual}

  {verdict}

  What was said beforehand:
  {_outcome_line(home, away, pred)}

One match says very little either way. The model's record over every completed
matchweek is on the site, which is the number worth judging it by.
"""
    text, html = _notification(core, unsubscribe_url)
    return subject, text, html


def confirm_subscription(confirm_url: str) -> tuple[str, str, str]:
    """(subject, text, html) for the double opt-in email."""
    subject = "Confirm your EPL Predictor notifications"

    lead = """Someone - probably you - asked for match predictions to be sent to this
address.
"""
    rest = """You will get two emails per match you follow: the prediction shortly before
kickoff, and the result with how the call went shortly after the final whistle.

If this was not you, ignore this email. Nothing is sent to an address that has
not confirmed, so there is nothing to unsubscribe from and no further messages
will arrive.
"""
    text = f"""{lead}
Confirm to start receiving them:

{confirm_url}

{rest}
-
{SIGNATURE}
Privacy: {privacy_url()}
"""
    html = render(
        lead,
        actions=button("Confirm subscription", confirm_url),
        after=rest,
        footer=(
            f"{_html.escape(SIGNATURE)}<br>"
            f"<a href=\"{_html.escape(privacy_url(), quote=True)}\">Privacy</a>"
        ),
    )
    return subject, text, html
