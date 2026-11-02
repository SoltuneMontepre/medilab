from typing import TYPE_CHECKING

from psycopg2 import IntegrityError

from odoo import fields, models
from odoo.tools import SQL, mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FILE_READ,
    FILE_WRITE,
    LOCKABLE_CATEGORIES,
    LOCKED,
    NOT_LOCKABLE,
    NOT_LOCKED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileBase
else:
    LaboratoryFileBase = object


# Tệp Phòng Thí Nghiệm
class LaboratoryFile(models.Model, LaboratoryFileBase):
    _inherit = MODEL_LABORATORY_FILE

    if not TYPE_CHECKING:
        # Every lock taken on the file.
        lock_ids = fields.One2many(MODEL_LABORATORY_FILE_LOCK, "file_id", string="Locks")
        # The lock in force on the file; empty when nobody holds one or it expired.
        lock_id = fields.Many2one(MODEL_LABORATORY_FILE_LOCK, string="Lock", compute="_compute_lock")
        # The user holding the lock in force.
        locked_by_id = fields.Many2one(MODEL_RES_USERS, string="Locked By", compute="_compute_lock")
        # When the lock in force expires unless renewed.
        locked_until = fields.Datetime(string="Locked Until", compute="_compute_lock")

    def _compute_lock(self):
        # Computed together rather than related to the lock, which is not stored: a lock's expiry changes as it is
        # renewed, and Odoo cannot find the files of a field it does not store.
        locks = self._locks_in_force()
        for file in self:
            lock = locks.filtered(lambda lock, file=file: lock.file_id == file)[:1]
            file.lock_id = lock
            file.locked_by_id = lock.user_id
            file.locked_until = lock.expires_at

    def _locks_in_force(self):
        return (
            self.env[MODEL_LABORATORY_FILE_LOCK]
            .sudo()
            .search(
                [("file_id", "in", self.ids), ("status", "=", "active"), ("expires_at", ">", fields.Datetime.now())]
            )
        )

    def _lock_in_force(self):
        """The lock that holds on the file, or no lock: one that expired counts as none."""
        self.ensure_one()
        return self._locks_in_force()

    def _check_file_access(self, access):
        """Writing a file someone else has locked is refused, so callers refuse it before they act."""
        result = super()._check_file_access(access)
        if access == FILE_WRITE:
            self._check_not_locked_by_others(self.env.user)
        return result

    def _check_can_add_version(self, user, device):
        """No version of a file someone else has locked is stored, whoever stores it and with whatever rights."""
        result = super()._check_can_add_version(user, device)
        self._check_not_locked_by_others(user)
        return result

    def _check_not_locked_by_others(self, user):
        others = self._locks_in_force().filtered(lambda lock: lock.user_id != user)
        if others:
            raise LaboratoryFileError(LOCKED, others[0]._busy_message())

    def _is_lockable(self):
        """A file that is neither raw data nor an Office document, in a folder of working documents, of results or of no
        category."""
        self.ensure_one()
        return (
            not self._is_raw_data()
            and not self._is_office_document()
            and self.sudo().folder_id.category in LOCKABLE_CATEGORIES
        )

    def _lock(self, device=None):
        """Lock the file for the user from the device, for the lock duration, and return the lock; a lock the user
        already holds is renewed. Two people locking the file at once end with one holder: the second one's request runs
        again and is refused."""
        self.ensure_one()
        self._check_file_access(FILE_WRITE)
        if not self._is_lockable():
            raise LaboratoryFileError(
                NOT_LOCKABLE, self.env._("Raw data, Office documents and report files are not locked.")
            )
        self._serialize_with_saves()
        locks = self.env[MODEL_LABORATORY_FILE_LOCK].sudo()
        active = locks.search([("file_id", "=", self.id), ("status", "=", "active")])
        # A lock in force is the user's own: the access check refused anyone else's.
        own = active._in_force()
        (active - own)._expire()
        if own:
            own.expires_at = locks._new_expiry()
            return own.with_env(self.env)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                lock = locks.create(
                    {
                        "file_id": self.id,
                        "user_id": self.env.uid,
                        "device_id": device.id if device else False,
                        "expires_at": locks._new_expiry(),
                    }
                )
        except IntegrityError:
            raise LaboratoryFileError(LOCKED, self.env._("Someone else has just locked %s.", self.path)) from None
        return lock.with_env(self.env)

    def _renew_lock(self):
        """Renew the user's lock on the file for the lock duration and return it. A lock that expired is not renewed:
        someone may have saved the file meanwhile, so the user locks it again."""
        self.ensure_one()
        self._check_file_access(FILE_WRITE)
        own = self._lock_in_force().filtered(lambda lock: lock.user_id == self.env.user)
        if not own:
            raise LaboratoryFileError(
                NOT_LOCKED, self.env._("You no longer hold a lock on %s; lock it again.", self.path)
            )
        own.expires_at = own._new_expiry()
        return own.with_env(self.env)

    def _unlock(self):
        """Release the user's lock on the file. A user holding none has nothing to release, so unlocking twice does no
        harm. Reading the folder is enough, so a holder still unlocks a folder turned off meanwhile."""
        self.ensure_one()
        self._check_file_access(FILE_READ)
        locks = self.env[MODEL_LABORATORY_FILE_LOCK].sudo()
        own = locks.search([("file_id", "=", self.id), ("status", "=", "active"), ("user_id", "=", self.env.uid)])
        in_force = own._in_force()
        (own - in_force)._expire()
        in_force._release()

    def _serialize_with_saves(self):
        # Locking updates the file's row as every save does, so a save or another lock of the file that started
        # meanwhile fails with a serialization error and Odoo runs its request again, when it sees this lock. Locking
        # the row without changing it would not make it fail. The row keeps its values, such as when it was last saved.
        self.flush_recordset()
        self.env.cr.execute(SQL("UPDATE medilab_laboratory_file SET write_date = write_date WHERE id = %s", self.id))
