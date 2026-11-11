from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_ADMINISTER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_RES_USERS,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_lock as LaboratoryFileLockBase
else:
    LaboratoryFileLockBase = object


# Khóa Tệp Phòng Thí Nghiệm
class LaboratoryFileLock(models.Model, LaboratoryFileLockBase):
    _name = MODEL_LABORATORY_FILE_LOCK
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory File Lock"
    _order = "id desc"
    # Locks are taken, renewed and unlocked through the laboratory files API; administrators release one someone left
    # as folder administrators.
    _permission_actions = ("read",)
    # The trail records taking a lock and how it ended; renewing it only moves when it expires.
    _audit_exclude = ("expires_at",)

    if not TYPE_CHECKING:
        # The file locked.
        file_id = fields.Many2one(
            MODEL_LABORATORY_FILE, string="File", required=True, ondelete="restrict", readonly=True
        )
        # The folder of the file.
        folder_id = fields.Many2one(related="file_id.folder_id", string="Folder")
        # The user holding the lock.
        user_id = fields.Many2one(MODEL_RES_USERS, string="Holder", required=True, ondelete="restrict", readonly=True)
        # The device the lock was taken from.
        device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, string="Computer", ondelete="set null", readonly=True)
        # active, released or expired; a file has at most one active lock.
        status = fields.Selection(
            [("active", "Active"), ("released", "Released"), ("expired", "Expired")],
            required=True,
            default="active",
            readonly=True,
        )
        # When the lock expires unless renewed.
        expires_at = fields.Datetime(string="Expires On", required=True, readonly=True)
        # When the lock was released or expired.
        released_at = fields.Datetime(string="Ended On", readonly=True)
        # The administrator who released a lock someone left; empty when its holder released it.
        released_by_id = fields.Many2one(MODEL_RES_USERS, string="Released By", ondelete="restrict", readonly=True)

    _active_unique = models.UniqueIndex("(file_id) WHERE status = 'active'", "Someone else has just locked this file.")
    _file_status_index = models.Index("(file_id, status)")

    @api.depends("file_id.path", "user_id.name")
    def _compute_display_name(self):
        for lock in self:
            lock.display_name = f"{lock.file_id.path} ({lock.user_id.name})"

    def _audit_parents(self):
        # A lock is part of its file's history.
        return {lock.id: (MODEL_LABORATORY_FILE, lock.file_id.id) for lock in self.sudo()}

    @api.model
    def _duration(self):
        return timedelta(minutes=self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_file_lock_minutes"))

    @api.model
    def _new_expiry(self):
        return fields.Datetime.now() + self._duration()

    def _in_force(self):
        """The locks that hold: active and not expired. Every rule treats an expired lock as absent, whether or not the
        job has expired it yet."""
        now = fields.Datetime.now()
        return self.filtered(lambda lock: lock.status == "active" and lock.expires_at and lock.expires_at > now)

    @api.model
    def _stale(self):
        """The active locks past their expiry, which the job expires."""
        return self.sudo().search([("status", "=", "active"), ("expires_at", "<=", fields.Datetime.now())])

    def _expire(self):
        # A lock ended when it expired, not when the job or the next person found it.
        for lock in self.sudo().filtered(lambda lock: lock.status == "active"):
            lock.write({"status": "expired", "released_at": lock.expires_at})

    def _release(self, administrator=None):
        self.sudo().filtered(lambda lock: lock.status == "active").write(
            {
                "status": "released",
                "released_at": fields.Datetime.now(),
                "released_by_id": administrator.id if administrator else False,
            }
        )

    def _busy_message(self):
        self.ensure_one()
        return self.env._(
            "%(user)s has locked %(file)s until %(until)s.",
            user=self.user_id.name,
            file=self.file_id.path,
            until=format_datetime(self.env, self.expires_at, tz=self.env.user.tz, dt_format="short"),
        )

    @api.model
    def _cleanup_domain(self, cutoff):
        """The locks the cleanup job removes: released or expired before the cutoff."""
        return [("status", "!=", "active"), ("released_at", "<", cutoff)]

    def action_release(self):
        """Release locks someone left, as an administrator of their folders. A lock already past its expiry is recorded
        as expired."""
        locks = self.sudo()
        locks.folder_id.with_env(self.env)._check_folder_access(FOLDER_ADMINISTER)
        if any(lock.status != "active" for lock in locks):
            raise UserError(self.env._("Only an active lock can be released."))
        in_force = locks._in_force()
        (locks - in_force)._expire()
        in_force._release(self.env.user)
