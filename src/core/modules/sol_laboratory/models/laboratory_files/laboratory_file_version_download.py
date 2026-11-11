from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_version as LaboratoryFileVersionDownloadBase
else:
    LaboratoryFileVersionDownloadBase = object


# Phiên Bản Tệp: downloading a version from the back office.
class LaboratoryFileVersionDownload(models.Model, LaboratoryFileVersionDownloadBase):
    _inherit = MODEL_LABORATORY_FILE_VERSION

    def action_download(self):
        """Download the version's content straight from the bucket, through a presigned address, once the user may read
        its file; the bytes never pass through Odoo."""
        self.ensure_one()
        address, _expires_at = self.file_id._download_address(self)
        return {"type": "ir.actions.act_url", "url": address, "target": "new"}
