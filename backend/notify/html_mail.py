"""The HTML wrapper around a plain-text message.

Kept deliberately small. Mail clients agree on very little - Outlook still lays
out with tables, Gmail strips <style> blocks, and dark mode inverts whatever it
feels like - so this uses inline styles, one table, system fonts and no images.
The text is the message; the HTML only adds a button where the text has a URL.

`render` takes the same words the plain-text version uses, so the two cannot
drift. It escapes everything, which is the point of having one function do it:
a club name is data from an upstream feed, and it is rendered, not trusted.
"""

from __future__ import annotations

import html

# Colours match the site's own: the navy the masthead uses, and the slate the
# body text uses. A quiet button is for the action a reader should be able to
# find but is not being asked to take.
NAVY = "#37003c"
TEXT = "#1f2733"
MUTED = "#586274"
RULE = "#e5e7eb"


def button(label: str, href: str, quiet: bool = False) -> str:
    """A link styled as a button. The href is where the token lives.

    Rendered as an anchor with padding rather than a <button>, because a
    <button> inside an email does nothing in most clients. The label is what
    the reader sees; the URL is not shown anywhere.
    """
    if quiet:
        style = (
            f"display:inline-block;padding:8px 16px;border:1px solid {RULE};"
            f"border-radius:6px;color:{MUTED};font-size:13px;font-weight:600;"
            "text-decoration:none;"
        )
    else:
        style = (
            f"display:inline-block;padding:12px 22px;background:{NAVY};"
            "border-radius:6px;color:#ffffff;font-size:15px;font-weight:700;"
            "text-decoration:none;"
        )
    return (
        f"<a href=\"{html.escape(href, quote=True)}\" style=\"{style}\">"
        f"{html.escape(label)}</a>"
    )


def _paragraphs(text: str) -> str:
    """Blank-line separated text to paragraphs; single newlines kept as breaks.

    Lines the text version indents with two spaces are the figures - scoreline,
    probabilities, verdict - and they are set in a monospace face so the columns
    line up the way they do in the plain text.
    """
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        mono = all(ln.startswith("  ") or not ln.strip() for ln in lines)
        if mono:
            body = "<br>".join(html.escape(ln.strip()) for ln in lines)
            out.append(
                f"<p style=\"margin:0 0 14px;font-family:ui-monospace,Menlo,Consolas,"
                f"monospace;font-size:14px;line-height:1.7;color:{TEXT};"
                f"white-space:nowrap;\">{body}</p>"
            )
        else:
            body = _reflow(lines)
            out.append(
                f"<p style=\"margin:0 0 14px;font-size:15px;line-height:1.6;"
                f"color:{TEXT};\">{body}</p>"
            )
    return "".join(out)


def _reflow(lines: list[str]) -> str:
    """Prose from the text version, with its hard wrap undone.

    The plain text is wrapped at about 78 columns for the sake of text-only
    clients. In HTML that wrap would land mid-sentence at whatever width the
    client uses, so a line that was wrapped - a long one followed by more text -
    is rejoined with a space. A short line is a deliberate break, like the two
    lines of the heading, and is kept.
    """
    out = ""
    for i, ln in enumerate(lines):
        piece = html.escape(ln.strip())
        if i == 0:
            out = piece
        elif len(lines[i - 1]) > 55:
            out += " " + piece
        else:
            out += "<br>" + piece
    return out


def render(core: str, actions: str, footer: str, after: str = "") -> str:
    """One message: `core` text, then the action button(s), then `after` text,
    then a rule and the footer. `footer` is already HTML; the rest is text."""
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    return f"""<!doctype html>
<html lang="en">
<body style="margin:0;padding:0;background:#f4f5f7;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:8px;font-family:{font};">
<tr><td style="padding:6px 28px 0;border-top:4px solid {NAVY};border-radius:8px 8px 0 0;"></td></tr>
<tr><td style="padding:20px 28px 4px;">
{_paragraphs(core)}
</td></tr>
<tr><td style="padding:6px 28px 18px;">
{actions}
</td></tr>
{f'<tr><td style="padding:0 28px 8px;">{_paragraphs(after)}</td></tr>' if after else ''}
<tr><td style="padding:14px 28px 22px;border-top:1px solid {RULE};font-size:12px;line-height:1.6;color:{MUTED};">
{footer}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
