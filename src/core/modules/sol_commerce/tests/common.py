from datetime import date

from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_SERVICE_PACKAGE, MODEL_TAX
from odoo.addons.sol_laboratory.tests.common import MasterDataCase


class PricingCase(MasterDataCase):
    """VAT 10% with a reduced 8% period in the first half of 2025, and the lead parameter priced with it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vat = cls.env[MODEL_TAX].create(
            {
                "code": "TEST-VAT10",
                "name": "VAT 10%",
                "rate_ids": [
                    Command.create({"rate": 8, "valid_from": date(2025, 1, 1), "valid_until": date(2025, 6, 30)}),
                    Command.create({"rate": 10, "valid_from": date(2025, 7, 1)}),
                ],
            }
        )
        cls.lead_price = cls.create_price(cls.parameter, 150000)

    @classmethod
    def create_price(cls, parameter, price, tax=None):
        """A price of the parameter that has applied since 2020."""
        return cls.env[MODEL_PARAMETER_PRICE].create(
            {
                "parameter_id": parameter.id,
                "tax_id": (tax or cls.vat).id,
                "period_ids": [Command.create({"list_price": price, "valid_from": date(2020, 1, 1)})],
            }
        )

    @classmethod
    def create_package(cls, *lines, code="PKG-1"):
        return cls.env[MODEL_SERVICE_PACKAGE].create(
            {
                "code": code,
                "name": "Heavy metals basic",
                "tax_id": cls.vat.id,
                "line_ids": [
                    Command.create({"parameter_id": parameter.id, "quantity": quantity})
                    for parameter, quantity in lines
                ],
            }
        )
