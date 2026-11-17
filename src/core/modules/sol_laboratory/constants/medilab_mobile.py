"""The refusals of Medilab Mobile's routes, the screens it opens documents on and the pages of its lists."""

# Turning off the push of a mandatory event.
MANDATORY_EVENT = "mandatory_event"
# The model refused the action a phone's route called; the message says why.
ACTION_REFUSED = "action_refused"
# Claiming a task someone else claimed first.
ALREADY_CLAIMED = "already_claimed"
# Signing a result whose warnings the person did not acknowledge.
RESULT_WARNING = "result_warning"
# Taking a support request someone else took first.
ALREADY_TAKEN = "already_taken"
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
# How many results waiting for the person's signature a page gives when the app names no limit.
RESULT_PAGE_SIZE = 50
# A file over its limit.
TOO_LARGE = "too_large"
# The largest photo a phone sends, once decoded.
PHOTO_MAX_BYTES = 10 * 1024 * 1024
# The largest signature a phone sends, once decoded.
SIGNATURE_MAX_BYTES = 1024 * 1024
# The bytes every PNG image starts with.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# How many handover records a page gives when the app names no limit.
HANDOVER_RECORD_PAGE_SIZE = 50
# The largest file a phone sends, once decoded.
FILE_MAX_BYTES = 10 * 1024 * 1024
# The largest total of the files of one request, once decoded.
REQUEST_FILES_MAX_BYTES = 25 * 1024 * 1024
# How many messages a page gives when the app names no limit.
MESSAGE_PAGE_SIZE = 30
# How many people a search for a conversation's member or a mention finds at most.
PEOPLE_LIMIT = 20
# The event of a push of a conversation message.
MESSAGE_EVENT = "message"
# The conversations of Medilab Mobile: direct conversations between two people and group conversations.
CONVERSATION_TYPES = ("chat", "group")
