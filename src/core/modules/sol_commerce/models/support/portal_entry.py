from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_PORTAL_ENTRY
from odoo.addons.sol_commerce.constants.xml_ids import SUPPORT_PORTAL_ENTRY
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

if TYPE_CHECKING:
    from medilab_model_types import Model_portal_entry as PortalEntryBase
else:
    PortalEntryBase = object


# Thẻ Cổng Khách Hàng: the Support card is shown to customers only.
class PortalEntry(models.Model, PortalEntryBase):
    _name = MODEL_PORTAL_ENTRY
    _inherit = MODEL_PORTAL_ENTRY

    def _filter_visible_portal_cards(self):
        cards = super()._filter_visible_portal_cards()
        if self.env[MODEL_CUSTOMER]._of_user(self.env.user):
            return cards
        return cards - self.env.ref(SUPPORT_PORTAL_ENTRY)
