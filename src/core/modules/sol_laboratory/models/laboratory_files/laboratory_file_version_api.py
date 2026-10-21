from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime


# Phiên Bản Tệp: a version as the laboratory files API gives it, once the person's access to its file is checked.
class LaboratoryFileVersionApi(models.Model):
    _inherit = MODEL_LABORATORY_FILE_VERSION

    def _laboratory_api_values(self):
        """The version as the laboratory files API gives it: its number, source, content's size and SHA-256, who saved
        it from which computer, and the versions it was made from. Its content's key is never given."""
        self.ensure_one()
        version = self.sudo()
        return {
            "id": version.id,
            "number": version.number,
            "source": version.source,
            "size": version.size,
            "sha256": version.sha256,
            "parent_version_id": version.parent_version_id.id or None,
            "restored_from_id": version.restored_from_id.id or None,
            "saved_by": {"id": version.user_id.id, "name": version.user_id.name},
            "device": {"id": version.device_id.id, "name": version.device_id.name} if version.device_id else None,
            "created_at": api_datetime(version.create_date),
        }
