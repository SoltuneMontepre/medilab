from ast import literal_eval
from datetime import datetime, time, timedelta
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .common import PricingCase
from .invoicing_case import InvoicingCase
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_ACCOUNT_PAYMENT,
    MODEL_PARAMETER_PRICE,
    MODEL_PRODUCT_TEMPLATE,
)
from odoo.addons.sol_commerce.models.invoicing.account_move import VIETNAM
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_GROUP, MODEL_PERMISSION, MODEL_PERSON

REPORTS = ("revenue", "outstanding", "cash_flow", "collection", "pending_payment")
REPORT_PERMISSIONS = ("revenue.report.read.all", "receivable.report.read.all", "cash.flow.report.read.all")


@tagged("post_install", "-at_install")
class TestFinanceReports(InvoicingCase, PricingCase):
    """Revenue spreads packages over their groups, the reports count confirmed payments only, the outstanding report
    ages each debt and the collection report measures how fast invoices are paid. Lead costs 150,000 VND in heavy
    metals, coliforms 50,000 VND in microbiology, and a package of one lead and two coliform tests 100,001 VND."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.microbiology = cls.env[MODEL_PARAMETER_GROUP].create({"name": "Microbiology"})
        cls.coliforms = cls.create_parameter("Coliforms", cls.microbiology)
        cls.env[MODEL_PARAMETER_PRICE].create(
            {"parameter_id": cls.coliforms.id, "list_price": 50000, "tax_id": cls.vat.id}
        )
        cls.package = cls.create_package(100001, (cls.parameter, 1), (cls.coliforms, 2))
        products = cls.env[MODEL_PRODUCT_TEMPLATE]
        cls.lead_product = products.search([("parameter_id", "=", cls.parameter.id)]).product_variant_id
        cls.package_product = products.search([("service_package_id", "=", cls.package.id)]).product_variant_id
        cls.today = datetime.now(VIETNAM).date()

    def invoice(self, lines, days_ago=0, due_in=0):
        """A posted final invoice of (product, quantity, unit price) lines, dated days ago and due days after."""
        invoice_date = self.today - timedelta(days=days_ago)
        invoice = self.env[MODEL_ACCOUNT_MOVE].create(
            {
                "move_type": "out_invoice",
                "invoice_kind": "final",
                "partner_id": self.partner.id,
                "invoice_date": invoice_date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "quantity": quantity,
                            "price_unit": price,
                            "tax_ids": [Command.clear()],
                        }
                    )
                    for product, quantity, price in lines
                ],
            }
        )
        invoice.invoice_date_due = invoice_date + timedelta(days=due_in)
        invoice.action_post()
        return invoice

    def pay(self, invoice, amount, days_ago=0, confirm=True):
        """A cash payment received days ago, confirmed by the accountant or left pending."""
        payment = self.env[MODEL_ACCOUNT_PAYMENT].create_pending_payment(invoice, amount, "cash")
        payment.date = self.today - timedelta(days=days_ago)
        if confirm:
            payment.action_post()
        return payment

    def report(self, name):
        """The report records the action shows, and its domain."""
        action = self.env.ref(f"sol_commerce.action_medilab_{name}_report")
        return self.env[action.res_model], literal_eval(action.domain or "[]")

    def test_a_package_line_is_spread_over_its_parameters_and_the_groups_add_up_to_the_invoice(self):
        invoice = self.invoice([(self.package_product, 1, 100001), (self.lead_product, 2, 150000)])
        revenue, domain = self.report("revenue")

        groups = dict(revenue._read_group(domain + [("name", "=", invoice.name)], ["group_id"], ["invoiced:sum"]))

        # The package's 100,001 VND is 60% lead (150,000 x 1) and 40% coliforms (50,000 x 2), rounded to the dong.
        self.assertEqual(groups, {self.group: 60001 + 300000, self.microbiology: 40000})
        self.assertEqual(sum(groups.values()), invoice.amount_untaxed)

    def test_a_pending_payment_counts_in_no_total_and_is_listed_separately(self):
        invoice = self.invoice([(self.lead_product, 1, 1_000_000)], due_in=30)
        self.pay(invoice, 400_000)
        pending = self.pay(invoice, 300_000, confirm=False)
        this_invoice = [("name", "=", invoice.name)]
        this_customer = [("partner_id", "=", self.partner.id)]

        revenue, revenue_domain = self.report("revenue")
        outstanding, outstanding_domain = self.report("outstanding")
        cash_flow, cash_flow_domain = self.report("cash_flow")
        _pending, pending_domain = self.report("pending_payment")
        [(collected,)] = revenue._read_group(revenue_domain + this_invoice, [], ["collected:sum"])
        [(owed,)] = outstanding._read_group(outstanding_domain + this_invoice, [], ["amount_owed:sum"])
        [(received,)] = cash_flow._read_group(cash_flow_domain + this_customer, [], ["amount:sum"])

        self.assertEqual((collected, owed, received), (400_000, 600_000, 400_000))
        self.assertEqual(cash_flow.search(pending_domain + this_customer).ids, pending.ids)

    def test_the_outstanding_report_ages_each_unpaid_invoice_from_its_due_date(self):
        overdue = self.invoice([(self.lead_product, 1, 150000)], days_ago=50, due_in=10)
        current = self.invoice([(self.lead_product, 1, 150000)], due_in=5)
        paid = self.invoice([(self.lead_product, 1, 150000)], days_ago=50, due_in=10)
        self.pay(paid, 150000)
        outstanding, domain = self.report("outstanding")

        rows = outstanding.search(domain + [("partner_id", "=", self.partner.id)])

        self.assertEqual(
            {row.name: (row.days_overdue, row.age) for row in rows},
            {overdue.name: (40, "31_60"), current.name: (0, "not_due")},
        )

    def test_collection_averages_the_days_to_pay_and_the_share_paid_on_time(self):
        on_time = self.invoice([(self.lead_product, 1, 150000)], days_ago=30, due_in=10)
        late = self.invoice([(self.lead_product, 1, 150000)], days_ago=30, due_in=10)
        still_open = self.invoice([(self.lead_product, 1, 150000)], days_ago=30, due_in=25)
        not_due = self.invoice([(self.lead_product, 1, 150000)], due_in=10)
        cleared = self.invoice([(self.lead_product, 1, 150000)], days_ago=30, due_in=10)
        sent = datetime.combine(self.today - timedelta(days=30), time(3))
        (on_time | late | still_open | not_due | cleared).write({"sent_at": sent})
        self.pay(on_time, 150000, days_ago=25)
        self.pay(late, 150000, days_ago=10)
        cleared.action_adjust(-150000)
        collection, domain = self.report("collection")
        domain += [("partner_id", "=", self.partner.id)]

        rows = collection.search(domain)
        [(days_to_pay, paid_on_time)] = collection._read_group(domain, [], ["days_to_pay:avg", "paid_on_time:avg"])

        self.assertEqual(
            {row.name: (row.timing, row.days_to_pay) for row in rows},
            {on_time.name: ("on_time", 5), late.name: ("late", 20), still_open.name: ("late", 0)},
        )
        self.assertEqual((days_to_pay, round(paid_on_time, 1)), (12.5, 33.3))

    def test_an_advance_invoice_is_sent_with_its_quotation_and_a_final_one_once_emailed(self):
        advance = self.order.create_advance_invoice()
        final = self.invoice([(self.lead_product, 1, 150000)])
        self.partner.email = "an@example.com"

        self.assertTrue(advance.sent_at)
        self.assertFalse(final.sent_at)
        with patch(
            "odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf",
            return_value=(b"%PDF", "pdf"),
        ):
            final.action_send_invoice()
        self.assertTrue(final.sent_at)

    def test_each_report_filters_by_period_and_customer_and_has_a_pivot_to_download(self):
        for name in REPORTS:
            action = self.env.ref(f"sol_commerce.action_medilab_{name}_report")
            search = etree.fromstring(self.env[action.res_model].get_view(view_type="search")["arch"])
            with self.subTest(report=name):
                self.assertTrue(search.xpath("//filter[@date]"))
                self.assertTrue(search.xpath("//field[@name='partner_id']"))
                # The pivot downloads as a spreadsheet as shown, without Odoo's export right.
                self.assertIn("pivot", action.view_mode.split(","))

    def test_the_reports_are_in_the_sales_reporting_menu_for_their_permission_holders_only(self):
        invoice = self.invoice([(self.package_product, 1, 100001)])
        permissions = self.env[MODEL_PERMISSION].search([("code", "in", REPORT_PERMISSIONS)])
        accountant = (
            self.env[MODEL_PERSON]
            .create(
                {"name": "Le Thi Hanh", "login": "accountant.reports", "permission_ids": [Command.set(permissions.ids)]}
            )
            .user_id
        )
        clerk = self.env[MODEL_PERSON].create({"name": "Hoang Van Duc", "login": "clerk.no.reports"}).user_id
        menus = {self.env.ref(f"sol_commerce.menu_{name}_report").id for name in REPORTS}
        revenue, domain = self.report("revenue")

        self.assertEqual(len(permissions), len(REPORT_PERMISSIONS))
        self.assertLessEqual(menus, self.env["ir.ui.menu"].with_user(accountant)._visible_menu_ids())
        self.assertFalse(menus & self.env["ir.ui.menu"].with_user(clerk)._visible_menu_ids())
        rows = revenue.with_user(accountant).search_read(domain + [("name", "=", invoice.name)], ["group_id"])
        self.assertEqual(len(rows), 2)
        with self.assertRaises(AccessError):
            revenue.with_user(clerk).search([])
