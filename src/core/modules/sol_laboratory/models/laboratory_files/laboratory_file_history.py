from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FILE_READ,
    FILE_WRITE,
    IDEMPOTENCY_CONFLICT,
    NOT_FOUND,
    RESTORED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_RES_CONFIG_SETTINGS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileHistoryBase
else:
    LaboratoryFileHistoryBase = object


# Tệp Phòng Thí Nghiệm: a file's history, downloading its versions and restoring one.
class LaboratoryFileHistory(models.Model, LaboratoryFileHistoryBase):
    _inherit = MODEL_LABORATORY_FILE

    def _not_a_version(self):
        return LaboratoryFileError(NOT_FOUND, self.env._("This version is not a version of the file."))

    def _version_of(self, version_id):
        """The version of the id of this file; a version of another file, or of no id, is not found."""
        self.ensure_one()
        version = self.sudo().version_ids.filtered(lambda row: row.id == version_id)
        if not version:
            raise self._not_a_version()
        return version.with_env(self.env)

    def _download_address(self, version):
        """The presigned address that downloads the version, for reading only, and when it stops working, once the user
        may read the file. It lasts the file address lifetime of the settings, and the download is recorded in the
        audit trail on the file. A version's content is downloaded only this way: knowing its SHA-256 gives nothing."""
        self.ensure_one()
        self._check_file_access(FILE_READ)
        if version.sudo().file_id != self.sudo():
            raise self._not_a_version()
        minutes = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_file_url_minutes")
        address = version._read_address(minutes * 60)
        self.sudo()._audit("download", self.env._("Version %s", version.sudo().number))
        return address, fields.Datetime.now() + timedelta(minutes=minutes)

    def _restore(self, version, device=None, key=None):
        """Restore the version of the file as its new current version, for the user from the computer, and return the
        version added: a restore always adds one, with the content of the version it restores. A request the computer
        repeats with its Idempotency-Key answers with the version it added."""
        self.ensure_one()
        self._check_file_access(FILE_WRITE)
        if version.sudo().file_id != self.sudo():
            raise self._not_a_version()
        versions = self.env[MODEL_LABORATORY_FILE_VERSION]
        if device and key:
            restored = versions._created_with_key(device, key)
            if restored:
                if restored.sudo().restored_from_id != version.sudo():
                    raise LaboratoryFileError(
                        IDEMPOTENCY_CONFLICT,
                        self.env._("This Idempotency-Key was already sent with another request."),
                    )
                return restored
        return self._add_version(
            source=RESTORED, user=self.env.user, device=device, restored_from=version, idempotency_key=key
        )
