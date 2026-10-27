from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.sol_commerce.hooks import use_vietnamese_accounting

PENDING_CHART = "_auto_install_template"


class TestVietnameseAccounting(TransactionCase):
    """A new database's company keeps prices, invoices and payments in VND on the Vietnamese chart."""

    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company_xmlid = "base.main_company"
        self.vnd = self.env.ref("base.VND")
        self.usd = self.env.ref("base.USD")
        self.addCleanup(vars(self.env.registry).pop, PENDING_CHART, None)

    def use_vietnamese_accounting(self, existing_accounting):
        with (
            patch.object(type(self.company), "_existing_accounting", return_value=existing_accounting),
            patch("odoo.addons.sol_commerce.hooks.MAIN_COMPANY", self.company_xmlid),
        ):
            use_vietnamese_accounting(self.env)

    def use_company_without_journal_items(self):
        self.company = self.env["res.company"].create({"name": "Generic chart fixture", "currency_id": self.usd.id})
        self.company_xmlid = "sol_commerce.test_generic_chart_company"
        self.env["ir.model.data"].create(
            {
                "module": "sol_commerce",
                "name": "test_generic_chart_company",
                "model": "res.company",
                "res_id": self.company.id,
            }
        )

    def test_the_company_has_the_vietnamese_chart_in_vnd_with_cash_and_bank_journals(self):
        self.assertEqual(self.company.chart_template, "vn")
        self.assertEqual(self.company.currency_id, self.vnd)
        self.assertEqual(self.company.country_id, self.env.ref("base.vn"))
        journals = self.env["account.journal"].search([("company_id", "=", self.company.id)])
        self.assertTrue({"cash", "bank", "sale"} <= set(journals.mapped("type")))

    def test_a_company_on_the_generic_chart_moves_to_vnd_and_the_vietnamese_chart(self):
        self.use_company_without_journal_items()
        self.company.write({"chart_template": "generic_coa", "currency_id": self.usd.id})
        pricelist = self.env["product.pricelist"].create(
            {"name": "Default", "company_id": self.company.id, "currency_id": self.usd.id}
        )

        self.use_vietnamese_accounting(existing_accounting=False)

        self.assertEqual(self.company.currency_id, self.vnd)
        self.assertEqual(self.company.country_id, self.env.ref("base.vn"))
        self.assertEqual(pricelist.currency_id, self.vnd)
        self.assertTrue(callable(getattr(self.env.registry, PENDING_CHART, None)))

    def test_a_company_with_journal_items_keeps_its_chart_and_currency(self):
        self.use_company_without_journal_items()
        self.company.write({"chart_template": "generic_coa", "currency_id": self.usd.id})

        with self.assertLogs("odoo.addons.sol_commerce.hooks", level="WARNING"):
            self.use_vietnamese_accounting(existing_accounting=True)

        self.assertEqual(self.company.chart_template, "generic_coa")
        self.assertEqual(self.company.currency_id, self.usd)
        self.assertFalse(hasattr(self.env.registry, PENDING_CHART))

    def test_a_company_on_the_vietnamese_chart_is_left_as_it_is(self):
        self.use_vietnamese_accounting(existing_accounting=False)

        self.assertEqual(self.company.chart_template, "vn")
        self.assertFalse(hasattr(self.env.registry, PENDING_CHART))
