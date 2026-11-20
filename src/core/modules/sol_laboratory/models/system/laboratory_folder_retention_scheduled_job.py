from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.laboratory_files import LABORATORY_FOLDER_RETENTION_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_SCHEDULED_JOB

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_laboratory_folder_retention_review(self):
        today = fields.Date.context_today(self)
        folders = (
            self.env[MODEL_LABORATORY_FOLDER]
            .sudo()
            .search(
                [
                    ("archived_at", "!=", False),
                    ("retention_until", "<=", today),
                    ("retention_review_required", "=", False),
                    ("retention_approved_at", "=", False),
                ]
            )
        )
        for folder in folders:
            self.queue(LABORATORY_FOLDER_RETENTION_JOB, f"folder:{folder.id}", document=folder)

    def _handle_laboratory_folder_retention_review(self, item):
        folder = item._document()
        if not folder or not folder.exists() or folder.retention_approved_at or folder.retention_review_required:
            return
        today = fields.Date.context_today(self)
        if folder.archived_at and folder.retention_until and folder.retention_until <= today:
            folder.sudo().write({"retention_review_required": True})
