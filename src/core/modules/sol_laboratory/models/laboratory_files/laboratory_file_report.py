from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.laboratory_editing import OPEN_STATUSES
from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_REPORT_TEMPLATE,
    MODEL_TEST_REPORT,
)
from odoo.addons.sol_laboratory.constants.xml_ids import REPORT_DRAFTS_FOLDER, REPORT_TEMPLATES_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file as LaboratoryFileBase
else:
    LaboratoryFileBase = object

# The model whose records own the files of each report folder, and the field naming the file.
REPORT_FOLDERS = {
    REPORT_TEMPLATES_FOLDER: (MODEL_REPORT_TEMPLATE, "file_id"),
    REPORT_DRAFTS_FOLDER: (MODEL_TEST_REPORT, "draft_file_id"),
}


# Tệp Phòng Thí Nghiệm: the DOCX files of report templates and report drafts, which their template or report gives
# access to, never folder membership, and which only online editing and MediLab itself write.
class LaboratoryFile(models.Model, LaboratoryFileBase):
    _inherit = MODEL_LABORATORY_FILE

    def _report_owner(self):
        """The template or report whose DOCX the file is, with full rights; None for a file of any other folder, and an
        empty record for a file of a report folder that no document owns."""
        self.ensure_one()
        folder = self.sudo().folder_id
        for xml_id, (model, field) in REPORT_FOLDERS.items():
            if folder == self.env.ref(xml_id, raise_if_not_found=False):
                return self.env[model].sudo().with_context(active_test=False).search([(field, "=", self.id)], limit=1)
        return None

    def _check_file_access(self, access):
        others = self.browse()
        for file in self:
            owner = file._report_owner()
            if owner is None:
                others |= file
            elif not owner:
                raise LaboratoryFileError(
                    NOT_FOUND, self.env._("This file does not exist or you do not have access to it.")
                )
            else:
                owner.with_env(self.env)._check_docx_access(access)
        if others:
            return super(LaboratoryFile, others)._check_file_access(access)
        return None

    def _check_can_add_version(self, user, device):
        result = super()._check_can_add_version(user, device)
        for file in self:
            owner = file._report_owner()
            if owner is None:
                continue
            if device or not owner:
                raise LaboratoryFileError(
                    PERMISSION_DENIED, self.env._("Report templates and drafts are only edited online.")
                )
            owner._check_docx_writable()
        return result

    def _open_editing_sessions(self):
        """The file's open editing sessions that are not idle: someone is editing it, or its save is not stored yet."""
        self.ensure_one()
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION].sudo()
        return sessions.search(
            [
                ("file_id", "=", self.id),
                ("status", "in", OPEN_STATUSES),
                ("last_activity_at", ">=", sessions._idle_cutoff()),
            ]
        )

    def _is_report_document(self):
        self.ensure_one()
        return self._report_owner() is not None
