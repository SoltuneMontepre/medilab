from contextlib import contextmanager
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import format_datetime, mute_logger

from odoo.addons.sol_laboratory.constants.locks import LOCK_BUS_TYPE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_DOCUMENT_LOCK,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_DOCUMENT_LOCK_RELEASED


# Khóa Chứng Từ
class DocumentLock(models.Model):
    _name = MODEL_DOCUMENT_LOCK
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Document Lock"
    _order = "id desc"
    # Locks are taken and released by editing and by long operations; administrators read them and release a stuck one.
    _permission_actions = ("read", "edit")

    # Technical name of the locked document.
    document_model = fields.Char(string="Document Type", required=True, readonly=True)
    # Id of the locked document.
    document_id = fields.Integer(string="Document ID", required=True, readonly=True)
    # The Odoo user holding the lock; for a long operation, the user who started it.
    user_id = fields.Many2one(MODEL_RES_USERS, string="Holder", required=True, ondelete="restrict", readonly=True)
    # edit for a user editing, or operation for a long operation such as sending a quotation.
    kind = fields.Selection(
        [("edit", "Editing"), ("operation", "Operation")], required=True, default="edit", readonly=True
    )
    # Last activity of the holder; the lock expires after the inactivity period from here.
    last_activity_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    # active, released or expired.
    status = fields.Selection(
        [("active", "Active"), ("released", "Released"), ("expired", "Expired")],
        required=True,
        default="active",
        readonly=True,
    )
    # When the lock was released or expired.
    released_at = fields.Datetime(readonly=True)
    # saved, cancelled, left, completed, expired or released_by_administrator.
    release_reason = fields.Selection(
        [
            ("saved", "Saved"),
            ("cancelled", "Cancelled"),
            ("left", "Left"),
            ("completed", "Completed"),
            ("expired", "Expired"),
            ("released_by_administrator", "Released by Administrator"),
        ],
        readonly=True,
    )
    # Administrator who released a stuck lock.
    released_by_id = fields.Many2one(MODEL_RES_USERS, ondelete="restrict", readonly=True)
    # Users waiting to be told when the lock is released.
    watcher_ids = fields.Many2many(
        MODEL_RES_USERS, "medilab_document_lock_watcher_rel", "lock_id", "user_id", string="Watchers", readonly=True
    )

    _active_unique = models.UniqueIndex(
        "(document_model, document_id) WHERE status = 'active'", "Someone else has just locked this document."
    )
    _document_index = models.Index("(document_model, document_id)")
    _stale_index = models.Index("(status, last_activity_at)")

    def _compute_display_name(self):
        for model, locks in self.grouped("document_model").items():
            documents = self.env[model].sudo().browse(locks.mapped("document_id")).exists() if model in self.env else []
            names = {document.id: document.display_name for document in documents}
            for lock in locks:
                lock.display_name = names.get(lock.document_id) or f"{model},{lock.document_id}"

    def _document(self):
        self.ensure_one()
        if self.document_model not in self.env:
            return None
        return self.env[self.document_model].sudo().browse(self.document_id).exists() or None

    @api.model
    def _timeout(self):
        return timedelta(minutes=self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("lock_timeout_minutes"))

    @api.model
    def _cutoff(self):
        """The last activity before which a lock is no longer in force."""
        return fields.Datetime.now() - self._timeout()

    def _fresh(self):
        """The locks whose holder was active within the inactivity period."""
        if not self:
            return self
        cutoff = self._cutoff()
        return self.filtered(lambda lock: lock.last_activity_at >= cutoff)

    @api.model
    def _active(self, documents):
        return self.sudo().search(
            [("document_model", "=", documents._name), ("document_id", "in", documents.ids), ("status", "=", "active")]
        )

    @api.model
    def _live(self, documents):
        """The locks in force on the documents. Locks past the inactivity period expire here, so a closed browser does
        not block a document until the next job run."""
        locks = self._active(documents)
        fresh = locks._fresh()
        (locks - fresh)._release("expired")
        return fresh

    def _of_others(self):
        return self.filtered(lambda lock: lock.user_id != self.env.user)

    def _own_edits(self):
        return self.filtered(lambda lock: lock.user_id == self.env.user and lock.kind == "edit")

    def _busy_message(self):
        self.ensure_one()
        values = {
            "user": self.user_id.name,
            "document": self.display_name,
            "since": format_datetime(self.env, self.create_date, tz=self.env.user.tz, dt_format="short"),
        }
        if self.kind == "operation":
            return self.env._("%(document)s is being processed by %(user)s since %(since)s.", **values)
        return self.env._("%(user)s is editing %(document)s since %(since)s.", **values)

    @api.model
    def _take(self, document, kind="edit"):
        """Lock the document for the current user, or refresh the user's own editing lock. A user's editing lock
        gives way to their own operation, as their form saved before the operation started."""
        document.ensure_one()
        live = self._live(document)
        blocking = live._of_others()
        if blocking:
            raise UserError(blocking._busy_message())
        own = live - blocking
        if own.kind == "operation":
            raise UserError(own._busy_message())
        if own and kind == "edit":
            own.last_activity_at = fields.Datetime.now()
            return own
        own._release("saved")
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                lock = self.sudo().create(
                    {
                        "document_model": document._name,
                        "document_id": document.id,
                        "user_id": self.env.uid,
                        "kind": kind,
                    }
                )
        except IntegrityError:
            raise UserError(self.env._("Someone else has just locked %s.", document.display_name)) from None
        lock._send_bus()
        return lock

    @api.model
    @contextmanager
    def _operation(self, documents):
        """Hold an operation lock on each document while the block runs, so a second start of the same operation is
        refused instead of running it twice. Locking the document rows refuses a concurrent start at once, while the
        lock rows are only visible once the transaction ends."""
        if documents.sudo().try_lock_for_update() != documents.sudo():
            # The document may not be readable from this transaction, so the message does not name it.
            raise UserError(self.env._("This document is already being processed; wait until it is done."))
        locks = self.sudo().browse()
        for document in documents:
            locks |= self._take(document, "operation")
        completed = False
        try:
            yield locks
            completed = True
        finally:
            # A failed block rolls the transaction back, and the lock rows with it; writing then would hide its error.
            if completed:
                locks._release("completed")

    def _release(self, reason, administrator=None):
        active = self.filtered(lambda lock: lock.status == "active")
        if not active:
            return
        active.sudo().write(
            {
                "status": "expired" if reason == "expired" else "released",
                "released_at": fields.Datetime.now(),
                "release_reason": reason,
                "released_by_id": administrator.id if administrator else False,
            }
        )
        for lock in active:
            lock._notify_watchers()
        active._send_bus()

    def _send_bus(self):
        # Every internal user's client listens on their groups; each open form reloads when its document is named.
        # An operation lock is taken and released in one transaction, so no other form ever sees it.
        employees = self.env.ref("base.group_user")
        for lock in self.filtered(lambda lock: lock.kind == "edit"):
            self.env["bus.bus"]._sendone(
                employees, LOCK_BUS_TYPE, {"model": lock.document_model, "id": lock.document_id}
            )

    def _notify_watchers(self):
        self.ensure_one()
        if not self.watcher_ids:
            return
        document = self._document()
        if not document:
            return
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_DOCUMENT_LOCK_RELEASED,
            document,
            f"document_lock:{self.id}:released",
            self.env._("%s is free to edit.", document.display_name),
            subject=document.display_name,
            partners=self.watcher_ids.partner_id,
        )

    @api.model
    def _watch(self, document):
        lock = self._active(document)._fresh()
        if not lock:
            raise UserError(self.env._("%s is not locked any more; you can edit it.", document.display_name))
        if lock.user_id != self.env.user:
            lock.sudo().watcher_ids = [Command.link(self.env.uid)]

    @api.model
    def _release_own(self, documents, reason):
        self._active(documents)._own_edits()._release(reason)

    @api.model
    def _cleanup_domain(self, cutoff):
        """The locks the cleanup job removes: released or expired before the cutoff."""
        return [("status", "!=", "active"), ("released_at", "<", cutoff)]

    @api.model
    def _stale(self):
        """The active locks whose holder was inactive for longer than the inactivity period."""
        return self.sudo().search([("status", "=", "active"), ("last_activity_at", "<", self._cutoff())])

    def action_release(self):
        self._check_permission("edit")
        locks = self.sudo()
        if any(lock.status != "active" for lock in locks):
            raise UserError(self.env._("Only an active lock can be released."))
        locks._release("released_by_administrator", self.env.user)
        for lock in locks:
            self.env[MODEL_AUDIT_ENTRY]._log_event(
                "unlock", self.env._("Lock of %s released", lock.user_id.name), lock._document()
            )
