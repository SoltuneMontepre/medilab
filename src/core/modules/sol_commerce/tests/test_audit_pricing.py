from odoo.tests import new_test_user, tagged

from .common import PricingCase
from odoo.addons.sol_laboratory.tests.audit_case import AUDITOR_GROUPS, AuditLookup


@tagged("post_install", "-at_install")
class TestAuditPricing(AuditLookup, PricingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.env.ref("base.user_admin")

    def test_changing_a_price_shows_who_changed_it_when_and_from_what_to_what(self):
        self.lead_price.with_user(self.administrator).list_price = 180000

        entry = self.entries(self.lead_price, "edit")
        self.assertEqual((entry.user_id, entry.source), (self.administrator, "screen"))
        self.assertTrue(entry.create_date)
        self.assertEqual(self.changes(entry), {"list_price": ("150000.0", "180000.0")})

    def test_the_history_of_a_parameter_shows_the_changes_to_its_price(self):
        auditor = new_test_user(self.env, login="auditor", groups=AUDITOR_GROUPS)
        self.lead_price.with_user(self.administrator).list_price = 180000

        self.assertIn(self.entries(self.lead_price, "edit"), self.history(self.parameter, auditor))

    def test_the_history_of_a_tax_shows_the_changes_to_its_rates(self):
        auditor = new_test_user(self.env, login="auditor", groups=AUDITOR_GROUPS)
        rate = self.vat.rate_ids.filtered(lambda rate: rate.rate == 8)

        rate.with_user(self.administrator).rate = 5

        self.assertIn(self.entries(rate, "edit"), self.history(self.vat, auditor))
