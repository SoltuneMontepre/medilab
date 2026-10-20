from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.locks import CLIENT_RELEASE_REASONS
from odoo.addons.sol_laboratory.constants.models import MODEL_DOCUMENT_LOCK, MODEL_LOCK_MIXIN


# Khóa Chứng Từ khi chỉnh sửa
class LockMixin(models.AbstractModel):
    _name = MODEL_LOCK_MIXIN
    _description = "Editing Lock"

    # Who else is editing the document and since when; empty while nobody else holds a lock on it.
    lock_message = fields.Char(string="Editing Lock", compute="_compute_lock_message")
    # True when the current user asked to be told when the document's lock is released.
    lock_watched = fields.Boolean(string="Watching Lock", compute="_compute_lock_message")

    @api.depends_context("uid")
    def _compute_lock_message(self):
        locks = self.env[MODEL_DOCUMENT_LOCK]._active(self.filtered("id"))._fresh()
        by_document = {lock.document_id: lock for lock in locks if lock.user_id != self.env.user}
        for document in self:
            lock = by_document.get(document.id)
            document.lock_message = lock._busy_message() if lock else False
            document.lock_watched = bool(lock) and self.env.user in lock.watcher_ids

    def write(self, vals):
        if self.env.su:
            return super().write(vals)
        locks = self._check_lock()
        result = super().write(vals)
        locks._own_edits()._release("saved")
        return result

    def unlink(self):
        if not self.env.su:
            self._check_lock()._own_edits()._release("left")
        return super().unlink()

    def _check_lock(self):
        """The locks in force on the documents, after refusing the change when another user holds one."""
        locks = self.env[MODEL_DOCUMENT_LOCK]._live(self)
        blocking = locks._of_others()
        if blocking:
            raise UserError(blocking[0]._busy_message())
        return locks

    def lock_take(self):
        """Called by the form when the user starts editing, and again while they keep editing."""
        self.ensure_one()
        self.check_access("write")
        try:
            self.env[MODEL_DOCUMENT_LOCK]._take(self)
        except UserError as error:
            return {"taken": False, "message": str(error)}
        return {"taken": True}

    def lock_release(self, reason):
        """Called by the form when the user cancels their changes or leaves the document."""
        if reason not in CLIENT_RELEASE_REASONS:
            raise UserError(self.env._("A form releases a lock only when cancelled or left."))
        self.env[MODEL_DOCUMENT_LOCK]._release_own(self, reason)

    def action_lock_watch(self):
        self.ensure_one()
        self.check_access("read")
        self.env[MODEL_DOCUMENT_LOCK]._watch(self)

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            self._add_lock_banner(arch)
        return arch, view

    @api.model
    def _add_lock_banner(self, arch):
        banner = etree.Element(
            "div",
            {"class": "alert alert-warning d-flex align-items-center gap-2 mb-0", "role": "alert"},
            invisible="not lock_message",
        )
        etree.SubElement(banner, "field", name="lock_message", readonly="1", nolabel="1", **{"class": "flex-grow-1"})
        etree.SubElement(
            banner,
            "button",
            name="action_lock_watch",
            type="object",
            string=self.env._("Notify me when free"),
            invisible="lock_watched",
            **{"class": "btn-secondary"},
        )
        # Below the header, so the banner is the first thing read on the document.
        header = arch.find("header")
        arch.insert(0 if header is None else arch.index(header) + 1, banner)
