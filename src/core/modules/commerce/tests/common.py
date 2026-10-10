from datetime import date

from odoo.fields import Command

from odoo.addons.commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_SERVICE_PACKAGE, MODEL_TAX
from odoo.addons.laboratory.tests.common import MasterDataCase


class PricingCase(MasterDataCase):
    """VAT 10% with a reduced 8% period in the first half of 2025, and the lead parameter priced with it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vat = cls.env[MODEL_TAX].create(
            {
                "code": "VAT10",
                "name": "VAT 10%",
                "rate_ids": [
                    Command.create({"rate": 8, "valid_from": date(2025, 1, 1), "valid_until": date(2025, 6, 30)}),
                    Command.create({"rate": 10, "valid_from": date(2025, 7, 1)}),
                ],
            }
        )
        cls.lead_price = cls.env[MODEL_PARAMETER_PRICE].create(
            {"parameter_id": cls.parameter.id, "list_price": 150000, "tax_id": cls.vat.id}
        )

    @classmethod
    def create_package(cls, list_price, *lines):
        return cls.env[MODEL_SERVICE_PACKAGE].create(
            {
                "code": f"PKG-{list_price}",
                "name": "Heavy metals basic",
                "list_price": list_price,
                "tax_id": cls.vat.id,
                "line_ids": [
                    Command.create({"parameter_id": parameter.id, "quantity": quantity})
                    for parameter, quantity in lines
                ],
            }
        )
