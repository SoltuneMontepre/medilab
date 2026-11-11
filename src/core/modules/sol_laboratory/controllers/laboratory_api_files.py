from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_READ, FOLDER_READ
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime, laboratory_api_route

# How many files or changes one call gives when the computer asks for no limit.
DEFAULT_LIMIT = 50


class LaboratoryApiFiles(http.Controller):
    """What a computer reads of a folder to sync it, a file's history, downloading a version straight from the bucket and
    restoring one. Renaming and deleting are never passed between computers."""

    def folder(self, device, folder_id):
        return device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)

    def file(self, device, folder_id, file_id):
        file = self.folder(device, folder_id)._file_of(file_id)
        file._check_file_access(FILE_READ)
        return file

    @laboratory_api_route("/folders/<int:folder_id>/files", ["GET"], "listFiles")
    def list_files(self, device, _body, folder_id, after="0", limit=None):
        limit = int(limit or DEFAULT_LIMIT)
        files = self.folder(device, folder_id)._files_after(int(after), limit + 1)
        return {
            "files": [file_values(file) for file in files[:limit]],
            "next_after": files[limit - 1].id if len(files) > limit else None,
        }

    @laboratory_api_route("/folders/<int:folder_id>/files/<int:file_id>/versions", ["GET"], "listVersions")
    def list_versions(self, device, _body, folder_id, file_id):
        file = self.file(device, folder_id, file_id)
        versions = file.sudo().version_ids.sorted("number", reverse=True).with_env(device.env)
        return {"versions": [version._laboratory_api_values() for version in versions]}

    @laboratory_api_route(
        "/folders/<int:folder_id>/files/<int:file_id>/versions/<int:version_id>/download", ["POST"], "downloadVersion"
    )
    def download_version(self, device, _body, folder_id, file_id, version_id):
        file = self.file(device, folder_id, file_id)
        url, expires_at = file._download_address(file._version_of(version_id))
        return {"url": url, "expires_at": api_datetime(expires_at)}

    @laboratory_api_route(
        "/folders/<int:folder_id>/files/<int:file_id>/versions/<int:version_id>/restore", ["POST"], "restoreVersion"
    )
    def restore_version(self, device, _body, folder_id, file_id, version_id, idempotency_key=None):
        file = self.file(device, folder_id, file_id)
        version = file._restore(file._version_of(version_id), device, idempotency_key)
        return {"version": version._laboratory_api_values()}

    @laboratory_api_route("/folders/<int:folder_id>/changes", ["GET"], "listChanges")
    def list_changes(self, device, _body, folder_id, after="0", limit=None):
        limit = int(limit or DEFAULT_LIMIT)
        changes = self.folder(device, folder_id)._changes_after(int(after), limit + 1)
        return {
            "changes": [change_values(change) for change in changes[:limit]],
            "next_after": changes[limit - 1].id if len(changes) > limit else None,
        }


def file_values(file):
    """A file as a computer syncs it: its path, its current version and the lock in force on it."""
    file = file.sudo()
    lock = file._lock_in_force()
    return {
        "id": file.id,
        "path": file.path,
        "current_version": file.current_version_id._laboratory_api_values() if file.current_version_id else None,
        "lock": file_lock_values(lock) if lock else None,
    }


def file_lock_values(lock):
    """The lock in force on a file as every member sees it: its holder and until when, never the computer."""
    return {
        "user": {"id": lock.user_id.id, "name": lock.user_id.name},
        "expires_at": api_datetime(lock.expires_at),
    }


def change_values(change):
    """A change: the file whose current version changed, and that version."""
    change = change.sudo()
    return {
        "id": change.id,
        "file": {"id": change.file_id.id, "path": change.file_id.path},
        "version": change.version_id._laboratory_api_values(),
    }
