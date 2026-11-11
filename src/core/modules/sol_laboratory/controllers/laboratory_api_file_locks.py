from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_READ
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime, laboratory_api_route


def lock_values(lock):
    """The person's own lock, with the computer they took it from."""
    return {
        "id": lock.id,
        "file_id": lock.file_id.id,
        "user": {"id": lock.user_id.id, "name": lock.user_id.name},
        "device_id": lock.device_id.id or None,
        "status": lock.status,
        "expires_at": api_datetime(lock.expires_at),
    }


class LaboratoryApiFileLocks(http.Controller):
    """A person locks a file they edit in their own program, so nobody else saves it until they unlock it or the lock
    expires. Administrators release a lock someone left in the back office."""

    def file_of(self, device, folder_id, file_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)
        return folder._file_of(file_id)

    @laboratory_api_route("/folders/<int:folder_id>/files/<int:file_id>/lock", ["POST"], "lockFile")
    def lock(self, device, _body, folder_id, file_id):
        # The lock records the computer of the key, the only one the call proves.
        lock = self.file_of(device, folder_id, file_id)._lock(device)
        return {"lock": lock_values(lock.sudo())}

    @laboratory_api_route("/folders/<int:folder_id>/files/<int:file_id>/lock/renew", ["POST"], "renewFileLock")
    def renew(self, device, _body, folder_id, file_id):
        lock = self.file_of(device, folder_id, file_id)._renew_lock()
        return {"lock": lock_values(lock.sudo())}

    @laboratory_api_route("/folders/<int:folder_id>/files/<int:file_id>/lock", ["DELETE"], "unlockFile")
    def unlock(self, device, _body, folder_id, file_id):
        self.file_of(device, folder_id, file_id)._unlock()
