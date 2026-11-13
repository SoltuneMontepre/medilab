"""The refusals of Medilab Mobile's routes, the screens it opens documents on and the pages of its lists."""

# Turning off the push of a mandatory event.
MANDATORY_EVENT = "mandatory_event"
# The model refused the action a phone's route called; the message says why.
ACTION_REFUSED = "action_refused"
# Claiming a task someone else claimed first.
ALREADY_CLAIMED = "already_claimed"
# The screen of a document the app has no screen of its own for: its code and title, and "Open on the web".
WEB_SCREEN = "web"
# The screen of a conversation, an Odoo Discuss channel.
CONVERSATION_SCREEN = "conversation"
# How many notifications a page gives when the app names no limit.
NOTIFICATION_PAGE_SIZE = 50
# How many tasks a page gives when the app names no limit.
TASK_PAGE_SIZE = 50
# How many people and how many departments a search for a task's assignee finds at most.
ASSIGNEE_LIMIT = 20
