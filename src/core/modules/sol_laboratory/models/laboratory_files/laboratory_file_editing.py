from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.laboratory_editing import NOT_EDITABLE, REPORT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION, MODEL_LABORATORY_FILE
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileBase
else:
    LaboratoryFileBase = object


# Tệp Phòng Thí Nghiệm
class LaboratoryFile(models.Model, LaboratoryFileBase):
    _inherit = MODEL_LABORATORY_FILE
    _audit_children = ("version_ids", "editing_session_ids")

    if not TYPE_CHECKING:
        # The online editing sessions of the file.
        editing_session_ids = fields.One2many(MODEL_LABORATORY_EDITING_SESSION, "file_id", string="Editing Sessions")

    def _check_can_edit_online(self):
        """Refuse a file that is not edited online: one that is not an Office document, or is in a raw-data or report
        folder. Office files of result and working folders and of folders without a category are edited online, once
        they have a version."""
        self.ensure_one()
        file = self.sudo()
        if not file._is_office_document() or file._is_raw_data() or file.folder_id.category == REPORT:
            raise LaboratoryFileError(
                NOT_EDITABLE,
                self.env._(
                    "Only Word, Excel and PowerPoint files of result and working folders are edited online; raw data "
                    "and reports never are."
                ),
            )
        if not file.current_version_id:
            raise LaboratoryFileError(NOT_EDITABLE, self.env._("This file has no version to edit yet."))
