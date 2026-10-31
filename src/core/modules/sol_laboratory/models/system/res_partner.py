from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.audit import MASK_PERSONAL
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_RES_PARTNER

if TYPE_CHECKING:
    from medilab_model_types import Model_res_partner as ResPartnerBase
else:
    ResPartnerBase = object

# How to reach and identify the contact, which the trail keeps only in part.
PERSONAL_FIELDS = frozenset(
    {
        "email",
        "email_normalized",
        "phone",
        "phone_sanitized",
        "street",
        "street2",
        "street_name",
        "street_number",
        "street_number2",
        "zip",
        "city",
        "vat",
    }
)


# Liên Hệ
class ResPartner(models.Model, ResPartnerBase):
    _name = MODEL_RES_PARTNER
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_RES_PARTNER]
    # When the person last dismissed their calendar alarms.
    _audit_exclude = ("calendar_last_notif_ack",)

    if not TYPE_CHECKING:
        # Contact name, searched with the subcontractor.
        name = fields.Char(index="trigram")

    def _audit_mask(self, field_name):
        if field_name in PERSONAL_FIELDS:
            return MASK_PERSONAL
        return super()._audit_mask(field_name)
