from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup


@tagged("post_install", "-at_install")
class TestAuditDocuments(AuditLookup, OrderCase):
    def test_every_commerce_document_is_audited(self):
        # The trail itself, which E-commerce extends with the route PayOS calls.
        self.assertEqual(self.unaudited_documents("sol_commerce"), {MODEL_AUDIT_ENTRY})

    def test_the_history_of_an_order_includes_its_quotation_sample_and_cancellation(self):
        auditor = self.new_auditor()
        order = self.make_quotable_order()
        order.sample_ids.customer_sample_name = "Renamed bottle"
        order.with_user(self.sales).action_send_quotation()
        quotation = order._latest_quotation()
        quotation.decline_reason = "Noted"
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        request = order.with_user(self.portal).action_request_cancellation("The sample changed")
        request.with_user(self.sales).reply = "Received"

        history = self.history(order, auditor)

        self.assertLessEqual(self.entries(order.sample_ids, "edit"), history)
        self.assertLessEqual(self.entries(quotation, "edit"), history)
        self.assertLessEqual(self.entries(request, "edit"), history)

    def test_editing_a_payment_is_recorded_and_the_entry_cannot_be_changed(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        invoice = order.sudo().invoice_ids[:1]
        payment = self.env["account.payment"].create_pending_payment(invoice, 100_000, "bank_transfer")
        before = self.entries(payment, "edit")

        payment.rejection_reason = "Not received"

        entry = self.entries(payment, "edit") - before
        self.assertEqual(self.changes(entry)["rejection_reason"], (False, "Not received"))
        with self.assertRaises(UserError):
            entry.write({"note": "changed"})
