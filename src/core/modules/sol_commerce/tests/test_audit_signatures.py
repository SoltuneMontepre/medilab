from odoo import fields
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_TAX
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_CHAIN, MODEL_AUDIT_REPORT
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup


@tagged("post_install", "-at_install")
class TestAuditSignatures(AuditLookup, OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chain = cls.env[MODEL_APPROVAL_CHAIN].search(
            [("document_model", "=", MODEL_SALE_ORDER), ("purpose", "=", PURPOSE_SIGNING)]
        )
        cls.sales_level, cls.head_level = cls.chain.level_ids.sorted("sequence")

    def test_each_signature_is_an_entry_and_the_last_one_approves(self):
        order = self.requested_order()

        order.with_user(self.head).action_sign()

        signs = self.entries(order, "sign").sorted("id")
        self.assertEqual(signs.mapped("note"), [self.sales_level.name, self.head_level.name])
        self.assertEqual(signs.user_id, self.sales | self.head)
        approve = self.entries(order, "approve")
        self.assertEqual((approve.note, approve.user_id), (self.chain.name, self.head))

    def test_a_rejection_records_its_reason(self):
        order = self.requested_order()

        order.with_user(self.head).action_reject("The price is below the cost of the tests")

        entry = self.entries(order, "reject")
        self.assertEqual(entry.note, f"{self.head_level.name}: The price is below the cost of the tests")
        self.assertEqual(entry.user_id, self.head)
        self.assertFalse(self.entries(order, "approve"))

    def test_withdrawing_a_signature_is_an_entry(self):
        order = self.requested_order()
        order.with_user(self.head).action_sign()

        order.with_user(self.head).action_withdraw()

        entry = self.entries(order, "withdraw")
        self.assertEqual((entry.note, entry.user_id), (self.head_level.name, self.head))

    def test_a_report_for_the_period_lists_every_signature_approval_and_deletion(self):
        auditor = self.new_auditor()
        today = fields.Date.context_today(auditor)
        order = self.requested_order()
        order.with_user(self.head).action_sign()
        tax = self.env[MODEL_TAX].create({"code": "TEST-VAT5", "name": "VAT 5%"})
        tax_name = tax.display_name
        tax.with_user(self.env.ref("base.user_admin")).unlink()

        report = self.env[MODEL_AUDIT_REPORT].with_user(auditor).create({"date_from": today, "date_to": today})
        rows = {(row["action"], row["document_type"], row["document"], row["note"]) for row in report._rows()}

        order_type = self.env["ir.model"]._get(MODEL_SALE_ORDER).name
        tax_type = self.env["ir.model"]._get(MODEL_TAX).name
        self.assertTrue(
            {
                ("Sign", order_type, order.display_name, self.sales_level.name),
                ("Sign", order_type, order.display_name, self.head_level.name),
                ("Approve", order_type, order.display_name, self.chain.name),
                ("Delete", tax_type, tax_name, tax_name),
            }
            <= rows
        )

    def test_the_token_that_opens_an_order_without_signing_in_is_masked(self):
        order = self.make_order([(self.lead_product, 1)])

        token = order._portal_ensure_token()

        changes = self.entries(order).change_ids.filtered(lambda change: change.field_name == "access_token")
        self.assertTrue(token)
        self.assertEqual(set(changes.mapped("new_value")), {"***"})
