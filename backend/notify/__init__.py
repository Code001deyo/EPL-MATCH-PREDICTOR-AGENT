"""Match notifications: who is subscribed, what they get, and when.

Barrel. `queue` decides what is due, `dispatch` sends it, `templates` owns the
wording. Subscriber storage and the send-once guarantee live in `db/subscribers.py`.
"""

# Exported as `send_due` rather than `dispatch`: a function named after its own
# submodule shadows it, so `from notify import dispatch` silently hands back the
# function and `notify.dispatch.dispatch` stops resolving.
from notify.dispatch import dispatch as send_due
from notify.queue import due_post_match, due_pre_match

__all__ = ["send_due", "due_pre_match", "due_post_match"]
