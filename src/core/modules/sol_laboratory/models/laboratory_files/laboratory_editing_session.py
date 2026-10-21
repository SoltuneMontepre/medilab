import hashlib
import hmac
import secrets
from datetime import timedelta

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, UserError, ValidationError
from odoo.tools import SQL, mute_logger
from odoo.tools.misc import hmac as database_hmac

from odoo.addons.sol_laboratory.constants.audit import MASK_SECRET
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    AUDIT_NOTE_CONTEXT,
    CALLBACK_TOKEN_SCOPE,
    CLOSED,
    COMMITTED,
    ERROR,
    EXPIRED,
    NEXT_STATUSES,
    OPEN,
    OPEN_STATUSES,
    SAVED_STATUSES,
    SAVING,
    SESSION_CONFLICT,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, FILE_WRITE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

# A session edits one version of one file for the person who opened it, under keys that never change.
IDENTITY_FIELDS = ("file_id", "base_version_id", "document_key", "callback_token", "opened_by_id")
# Bytes of randomness of a document key; its text stays within the 128 characters the editing service takes.
DOCUMENT_KEY_BYTES = 24


# Phiên Chỉnh Sửa Trực Tuyến
class LaboratoryEditingSession(models.Model):
    _name = MODEL_LABORATORY_EDITING_SESSION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Editing Session"
    _order = "id desc"
    # Opening a file online and the editing service's saves make and change sessions; they are never deleted.
    _permission_actions = ("read",)
    # Every call of the editing service moves it.
    _audit_exclude = ("last_activity_at",)

    # The file edited.
    file_id = fields.Many2one(MODEL_LABORATORY_FILE, string="File", required=True, ondelete="restrict", readonly=True)
    # The version the session opened; everyone in the session edits it.
    base_version_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Base Version", required=True, ondelete="restrict", readonly=True
    )
    # Key the editing service identifies the document by; new for every session.
    document_key = fields.Char(required=True, readonly=True, copy=False)
    # SHA-256 of the secret token in the address the editing service calls back on save; the token is never stored.
    callback_token = fields.Char(required=True, readonly=True, copy=False, audit_mask=MASK_SECRET)
    # open, saving, committed, conflict, closed, expired or error.
    status = fields.Selection(
        [
            (OPEN, "Open"),
            (SAVING, "Saving"),
            (COMMITTED, "Committed"),
            (SESSION_CONFLICT, "Conflict"),
            (CLOSED, "Closed"),
            (EXPIRED, "Expired"),
            (ERROR, "Error"),
        ],
        required=True,
        default=OPEN,
        readonly=True,
    )
    # The user who opened the session.
    opened_by_id = fields.Many2one(
        MODEL_RES_USERS, string="Opened By", required=True, ondelete="restrict", readonly=True
    )
    # The version the session saved: edited online, or a conflict; empty while open and when it saved nothing.
    committed_version_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Saved Version", ondelete="restrict", readonly=True, copy=False
    )
    # When someone last worked in the session; a session idle for the idle period expires.
    last_activity_at = fields.Datetime(
        string="Last Activity", required=True, default=fields.Datetime.now, readonly=True
    )

    _document_key_unique = models.Constraint("UNIQUE(document_key)", "Each editing session has its own document key.")
    _callback_token_unique = models.Constraint(
        "UNIQUE(callback_token)", "Each editing session has its own callback token."
    )
    _committed_version_unique = models.Constraint(
        "UNIQUE(committed_version_id)", "A version is saved by one editing session only."
    )
    _file_open_unique = models.UniqueIndex(
        f"(file_id) WHERE status IN ('{OPEN}', '{SAVING}')",
        "The file already has an open editing session; join it instead.",
    )
    _file_status_index = models.Index("(file_id, status)")

    @api.depends("file_id.path", "status")
    def _compute_display_name(self):
        statuses = dict(self._fields["status"]._description_selection(self.env))
        for session in self:
            session.display_name = self.env._(
                "%(path)s, %(status)s", path=session.file_id.path or "", status=statuses.get(session.status, "")
            )

    def write(self, vals):
        if set(IDENTITY_FIELDS) & set(vals):
            raise UserError(self.env._("An editing session keeps its file, its base version, its keys and its opener."))
        if "status" in vals and any(
            vals["status"] != session.status and vals["status"] not in NEXT_STATUSES[session.status] for session in self
        ):
            raise UserError(self.env._("An editing session that has ended cannot be opened again."))
        if vals.get("committed_version_id") and any(session.committed_version_id for session in self):
            raise UserError(self.env._("An editing session saves one version."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_session(self):
        raise UserError(self.env._("Editing sessions are never deleted."))

    @api.constrains("file_id", "base_version_id", "committed_version_id")
    def _check_versions(self):
        for session in self:
            versions = session.base_version_id | session.committed_version_id
            if versions.file_id != session.file_id:
                raise ValidationError(self.env._("An editing session opens and saves versions of its own file."))

    def _audit_notes(self):
        note = self.env.context.get(AUDIT_NOTE_CONTEXT)
        return dict.fromkeys(self.ids, note) if note else {}

    @api.model
    def _new_keys(self):
        """A new document key and the SHA-256 of the callback token derived from it, as a new session stores them."""
        document_key = secrets.token_urlsafe(DOCUMENT_KEY_BYTES)
        return document_key, self._token_hash(self._token_for(document_key))

    @api.model
    def _token_for(self, document_key):
        # Derived from the document key with the database's secret, so everyone who joins the session gets the same
        # callback address: the editing service calls back on the address of whoever changed the document last.
        return database_hmac(self.env(su=True), CALLBACK_TOKEN_SCOPE, document_key)

    @api.model
    def _token_hash(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _callback_token(self):
        """The secret token in the address the editing service calls back on save."""
        self.ensure_one()
        return self._token_for(self.sudo().document_key)

    @api.model
    def _from_callback_token(self, token):
        """The session the editing service calls back for with the token, or nothing."""
        if not token:
            return self.browse()
        token_hash = self._token_hash(token)
        session = self.sudo().search([("callback_token", "=", token_hash)], limit=1)
        if session.callback_token and hmac.compare_digest(session.callback_token, token_hash):
            return session
        return self.browse()

    @api.model
    def _open_for(self, file):
        """Open the file online for the user, once the user may write it, it is edited online and the editing service
        answers, and return its session."""
        file._check_file_access(FILE_WRITE)
        file._check_can_edit_online()
        self._check_editing_available()
        return self._join_or_open(file)

    @api.model
    def _join_or_open(self, file):
        """The file's open session, which the user joins even when the file has a newer version, or a new session on
        its current version when it has none or that one was idle for the idle period. Two people opening the file at
        once make one session: the second one's creation fails on the unique index, and Odoo runs its request again,
        when it joins the session."""
        sessions = self.sudo()
        session = sessions.search([("file_id", "=", file.id), ("status", "in", OPEN_STATUSES)], limit=1)
        if session and not session._is_idle():
            session._join(self.env.user)
            return session.with_env(self.env)
        session._expire()
        document_key, token_hash = sessions._new_keys()
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                session = sessions.create(
                    {
                        "file_id": file.id,
                        "base_version_id": file.sudo().current_version_id.id,
                        "document_key": document_key,
                        "callback_token": token_hash,
                        "opened_by_id": self.env.uid,
                    }
                )
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Committed by a transaction this one cannot see; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Someone else opened %s online meanwhile; it is opened again.", file.sudo().path)
            ) from error
        return session.with_env(self.env)

    def _join(self, user):
        self.ensure_one()
        self._touch()
        self._audit("edit", self.env._("%s joined the session.", user.name))

    def _touch(self):
        """Record activity in the sessions, which keeps them from expiring."""
        self.sudo().write({"last_activity_at": fields.Datetime.now()})

    def _store_save(self, *, content, editor, editors):
        """Store the editing service's save of the session, from the verified content the caller fetched and stored
        first, and return the version: edited online, a conflict when the file changed after the session opened, or the current
        version when the file already has the content. The version goes to the editor, the last person to change the
        document; editors are everyone who changed it.

        A session a save has already ended stores nothing and returns what it saved, as the editing service repeats a
        call it got no answer to. An expired session still saves. When the editor can no longer write the file, the
        session ends in error, recording the key of the stored content so it can be recovered, and nothing is stored."""
        self.ensure_one()
        session = self.sudo()
        session._lock()
        if session.status in SAVED_STATUSES:
            return session.committed_version_id.with_env(self.env)
        file = session.file_id
        current = file.current_version_id
        try:
            with self.env.cr.savepoint():
                file.with_user(editor)._check_file_access(FILE_WRITE)
                version = file._add_version(
                    content=content,
                    source=EDITED_ONLINE,
                    user=editor,
                    base_version=session.base_version_id,
                )
        except LaboratoryFileError as error:
            session._end_in_error(
                self.env._(
                    "%(person)s cannot save the file (%(reason)s); the saved content is kept under %(key)s.",
                    person=editor.name,
                    reason=error.args[0],
                    key=content.sudo().object_key,
                )
            )
            return self.env[MODEL_LABORATORY_FILE_VERSION]
        if version == current:
            status, saved = CLOSED, version.browse()
        else:
            status, saved = (SESSION_CONFLICT if version.source == CONFLICT else COMMITTED), version
        note = self.env._(
            "Saved by %(editor)s; edited by %(editors)s.",
            editor=editor.name,
            editors=", ".join((editor | editors).mapped("name")),
        )
        session.with_context(**{AUDIT_NOTE_CONTEXT: note}).write(
            {"status": status, "committed_version_id": saved.id, "last_activity_at": fields.Datetime.now()}
        )
        return version.with_env(self.env)

    def _close_unchanged(self):
        """End the session without a version: everyone left without changing the document."""
        self.ensure_one()
        session = self.sudo()
        session._lock()
        if session.status not in SAVED_STATUSES:
            session.write({"status": CLOSED, "last_activity_at": fields.Datetime.now()})

    def _keep_saving(self):
        """Record a save that failed for a while, such as the bucket being unreachable: the session waits for the
        editing service to call back again, and an expired session stays expired."""
        self.ensure_one()
        session = self.sudo()
        session._lock()
        if session.status not in SAVED_STATUSES:
            session.write(
                {
                    "status": SAVING if session.status == OPEN else session.status,
                    "last_activity_at": fields.Datetime.now(),
                }
            )

    def _fail(self, reason):
        """End the session in error, such as when the saved document cannot be read or the editing service could not
        save it, unless a save already ended it."""
        self.ensure_one()
        session = self.sudo()
        session._lock()
        if session.status not in SAVED_STATUSES:
            session._end_in_error(reason)

    def _end_in_error(self, reason):
        self.with_context(**{AUDIT_NOTE_CONTEXT: reason}).write(
            {"status": ERROR, "last_activity_at": fields.Datetime.now()}
        )

    @api.model
    def _idle(self):
        """The open sessions with no activity in the idle period."""
        return self.sudo().search([("status", "in", OPEN_STATUSES), ("last_activity_at", "<", self._idle_cutoff())])

    @api.model
    def _idle_cutoff(self):
        hours = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_editing_idle_hours")
        return fields.Datetime.now() - timedelta(hours=hours)

    def _is_idle(self):
        self.ensure_one()
        return bool(self.last_activity_at and self.last_activity_at < self._idle_cutoff())

    def _expire(self):
        """Expire the sessions still open and idle: nobody joins them any more, and their save is still stored when
        it arrives."""
        for session in self.sudo():
            session._lock()
            if session.status in OPEN_STATUSES and session._is_idle():
                session.status = EXPIRED
                session.flush_recordset(["status"])

    def _lock(self):
        # Updating the row locks it, as a file's row is locked for a new version: a concurrent call for the session
        # waits, then fails with a serialization error and Odoo runs its request again, when it sees what this one did.
        # Raw SQL, as the ORM only takes locks that do not wait.
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE medilab_laboratory_editing_session SET write_date = %s, write_uid = %s WHERE id = %s",
                fields.Datetime.now(),
                self.env.uid,
                self.id,
            )
        )
        self.invalidate_recordset()
