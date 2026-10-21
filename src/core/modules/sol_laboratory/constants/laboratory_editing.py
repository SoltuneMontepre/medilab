"""Statuses of online editing sessions and of the editing service's callbacks, the files edited online, the addresses,
secret and token header of the editing service, and the codes of their refusals."""

# The statuses of an editing session.
OPEN = "open"
SAVING = "saving"
COMMITTED = "committed"
SESSION_CONFLICT = "conflict"
CLOSED = "closed"
EXPIRED = "expired"
ERROR = "error"
# Open sessions, at most one per file: people join them.
OPEN_STATUSES = (OPEN, SAVING)
# Sessions a save has ended; a repeated call of the editing service stores nothing for them.
SAVED_STATUSES = (COMMITTED, SESSION_CONFLICT, CLOSED, ERROR)
# The statuses each status moves on to.
NEXT_STATUSES = {
    OPEN: frozenset({SAVING, COMMITTED, SESSION_CONFLICT, CLOSED, EXPIRED, ERROR}),
    SAVING: frozenset({COMMITTED, SESSION_CONFLICT, CLOSED, EXPIRED, ERROR}),
    EXPIRED: frozenset({COMMITTED, SESSION_CONFLICT, CLOSED, ERROR}),
    COMMITTED: frozenset(),
    SESSION_CONFLICT: frozenset(),
    CLOSED: frozenset(),
    ERROR: frozenset(),
}
# The category of a sample's folder that holds report drafts, whose files are not edited online.
REPORT = "report"
# The scope of the HMAC the callback token of a session is derived with.
CALLBACK_TOKEN_SCOPE = "sol_laboratory.editing_callback"
# The environment variable with the address Odoo reaches the editing service at; saved documents are fetched only from
# there.
INTERNAL_URL_VARIABLE = "ONLYOFFICE_INTERNAL_URL"
# Context key of the audit note of a session's write, such as the editors of its save.
AUDIT_NOTE_CONTEXT = "laboratory_editing_note"
# The key of the job that expires idle sessions.
EXPIRE_JOB = "laboratory_editing_sessions.expire"
# Code of the refusal of a file that is not edited online.
NOT_EDITABLE = "not_editable"
# Code of the refusal of opening a file while the editing service does not answer its health check.
EDITING_UNAVAILABLE = "editing_unavailable"
# The environment variable with the secret the editor configuration and the editing service's calls are signed with.
JWT_SECRET_VARIABLE = "ONLYOFFICE_JWT_SECRET"
# The header the editing service sends its token in: a name of our own, which no authentication of Odoo reads.
JWT_HEADER = "Medilab-Editor-Token"
# The statuses the editing service calls back with.
CALLBACK_EDITING = 1
CALLBACK_READY_TO_SAVE = 2
CALLBACK_SAVE_FAILED = 3
CALLBACK_CLOSED_UNCHANGED = 4
CALLBACK_FORCE_SAVED = 6
CALLBACK_FORCE_SAVE_FAILED = 7
# The environment variable with the address browsers reach the editing service at; the addresses of saved documents
# are on it.
PUBLIC_URL_VARIABLE = "ONLYOFFICE_PUBLIC_URL"
