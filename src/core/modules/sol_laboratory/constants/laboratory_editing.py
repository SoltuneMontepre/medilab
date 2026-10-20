"""Statuses of online editing sessions, the files edited online, the address the editing service is reached at, and the
codes of their refusals."""

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
# Code of the refusal of a file that is not edited online.
NOT_EDITABLE = "not_editable"
