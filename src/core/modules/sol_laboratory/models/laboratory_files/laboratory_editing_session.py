import hashlib
import hmac
import secrets

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL
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
    SAVING,
    SESSION_CONFLICT,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)

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

    def _lock(self):
        # Updating the row locks it, as a file's row is locked for a new version: a concurrent call for the session
        # waits, then fails with a serialization error and Odoo runs its request again, when it sees what this one did.
        # Raw SQL, as the ORM only takes locks that do not wait.
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE medilab_laboratory_editing_session SET last_activity_at = %s, write_date = %s, write_uid = %s"
                " WHERE id = %s",
                fields.Datetime.now(),
                fields.Datetime.now(),
                self.env.uid,
                self.id,
            )
        )
        self.invalidate_recordset()
