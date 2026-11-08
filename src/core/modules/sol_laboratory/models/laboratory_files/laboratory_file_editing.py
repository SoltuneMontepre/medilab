from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.laboratory_editing import NOT_EDITABLE, REPORT
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_WRITE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION, MODEL_LABORATORY_FILE
from odoo.addons.sol_laboratory.services.laboratory_editor_page import editor_path
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

    def action_open(self):
        """Open the file as a click on its row does: its editor page in a new tab, when the user may write it and it is
        edited online; its form otherwise. The editor page checks the user again and opens the session."""
        self.ensure_one()
        # Reading is the back office's own rule, the user's access and record rules, as the form applies it.
        self.check_access("read")
        try:
            self._check_file_access(FILE_WRITE)
            self._check_can_edit_online()
        except LaboratoryFileError:
            return {
                "type": "ir.actions.act_window",
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "views": [(False, "form")],
            }
        return {"type": "ir.actions.act_url", "url": editor_path(self.id), "target": "new"}

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
