from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP


# Tệp Đính Kèm
class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        # Photos of a sample are shown wherever the customer's name for the sample is shown.
        reader = self.env.ref(TEST_REQUEST_READER_GROUP).id
        if self.env.su or self.env.is_system() or reader in self.env.user._get_group_ids():
            return domain
        return domain & Domain("res_model", "!=", MODEL_SAMPLE)
