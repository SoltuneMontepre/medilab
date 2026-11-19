from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_person as PersonBase
else:
    PersonBase = object


# Nhân Sự: whether Medilab Mobile shows the person the support requests.
class Person(models.Model, PersonBase):
    _inherit = MODEL_PERSON

    @api.model
    def _mobile_can(self):
        return {**super()._mobile_can(), "take_support_requests": self.env[MODEL_SUPPORT_REQUEST]._may_handle()}
