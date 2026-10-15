from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_ACTIONS_REPORT


# Báo Cáo In
class IrActionsReport(models.Model):
    _inherit = MODEL_IR_ACTIONS_REPORT

    def _audit_download(self, res_ids):
        """Record that the current user downloaded this report of the documents, when they are audited."""
        self.ensure_one()
        if res_ids and self.env[MODEL_AUDIT_MIXIN]._audit_is_audited(self.model):
            self.env[self.model].browse(res_ids)._audit("download", self.name)
