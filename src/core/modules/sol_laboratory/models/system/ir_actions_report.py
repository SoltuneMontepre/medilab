from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_ACTIONS_REPORT
from odoo.addons.sol_laboratory.services.model_lookup import model_as

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_actions_report as IrActionsReportBase
else:
    IrActionsReportBase = object


# Báo Cáo In
class IrActionsReport(models.Model, IrActionsReportBase):
    _inherit = MODEL_IR_ACTIONS_REPORT

    def _audit_download(self, res_ids):
        """Record that the current user downloaded this report of the documents, when they are audited."""
        self.ensure_one()
        if res_ids and self.env[MODEL_AUDIT_MIXIN]._audit_is_audited(self.model):
            model_as(self.env, self.model, self.env[MODEL_AUDIT_MIXIN]).browse(res_ids)._audit("download", self.name)
