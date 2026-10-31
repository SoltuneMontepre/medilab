from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileSigningBase
else:
    LaboratoryFileSigningBase = object


# Tệp Phòng Thí Nghiệm: whether the version people get is signed.
class LaboratoryFileSigning(models.Model, LaboratoryFileSigningBase):
    _inherit = MODEL_LABORATORY_FILE

    if not TYPE_CHECKING:
        # Where the current version is in its signing; a newer version starts unsigned.
        current_approval_state = fields.Selection(related="current_version_id.approval_state", string="Signing")

    def _lock_for_signing(self):
        # Signing a version takes the file's row as a save does, so a signature and a concurrent save of the file wait
        # for each other and the second one runs again, seeing which version is current. It changes nothing, so the
        # file's last save stays as it was.
        self.env.cr.execute(
            SQL("UPDATE medilab_laboratory_file SET write_date = write_date WHERE id IN %s", tuple(self.ids))
        )
