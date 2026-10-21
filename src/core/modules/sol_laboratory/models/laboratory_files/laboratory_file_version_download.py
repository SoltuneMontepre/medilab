from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION


# Phiên Bản Tệp: downloading a version from the back office.
class LaboratoryFileVersionDownload(models.Model):
    _inherit = MODEL_LABORATORY_FILE_VERSION

    def action_download(self):
        """Download the version's content straight from the bucket, through a presigned address, once the user may read
        its file; the bytes never pass through Odoo."""
        self.ensure_one()
        address, _expires_at = self.file_id._download_address(self)
        return {"type": "ir.actions.act_url", "url": address, "target": "new"}
