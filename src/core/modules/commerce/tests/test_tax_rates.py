from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import PricingCase
from odoo.addons.commerce.constants.models import MODEL_TAX_RATE


@tagged("post_install", "-at_install")
class TestTaxRates(PricingCase):
    def test_rate_in_force_on_a_date(self):
        self.assertEqual(self.vat._rate_on(date(2025, 3, 15)), 8)
        self.assertEqual(self.vat._rate_on(date(2025, 6, 30)), 8)
        self.assertEqual(self.vat._rate_on(date(2025, 7, 1)), 10)
        self.assertEqual(self.vat._rate_on(date(2026, 10, 10)), 10)

    def test_date_without_rate_is_refused(self):
        with self.assertRaises(UserError):
            self.vat._rate_on(date(2024, 12, 31))

    def test_overlapping_period_is_refused(self):
        for valid_from, valid_until in (
            (date(2025, 6, 1), date(2025, 6, 15)),
            (date(2024, 12, 1), date(2025, 1, 1)),
            (date(2026, 1, 1), False),
            (date(2024, 1, 1), False),
        ):
            with self.subTest(valid_from=valid_from, valid_until=valid_until), self.assertRaises(ValidationError):
                self.env[MODEL_TAX_RATE].create(
                    {"tax_id": self.vat.id, "rate": 5, "valid_from": valid_from, "valid_until": valid_until}
                )

    def test_adjacent_period_is_accepted(self):
        self.env[MODEL_TAX_RATE].create(
            {"tax_id": self.vat.id, "rate": 10, "valid_from": date(2024, 1, 1), "valid_until": date(2024, 12, 31)}
        )

        self.assertEqual(self.vat._rate_on(date(2024, 12, 31)), 10)
