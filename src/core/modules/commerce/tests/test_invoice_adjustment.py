from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .invoicing_case import InvoicingCase


@tagged("post_install", "-at_install")
class TestInvoiceAdjustment(InvoicingCase):
    def test_a_lowering_adjustment_reduces_what_is_owed_and_leaves_the_original_unchanged(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        before = (invoice.code, invoice.amount_total, invoice.line_ids.mapped("amount_untaxed"), invoice.status)

        adjustment = self.create_invoice(lines=((-500_000, 0),), kind="adjustment", adjusts_id=invoice.id)

        self.assertEqual(adjustment.amount_total, -500_000)
        self.assertEqual(invoice.amount_adjustment, -500_000)
        self.assertEqual(invoice.amount_owed, 4_500_000)
        self.assertEqual((invoice.code, invoice.amount_total, invoice.line_ids.mapped("amount_untaxed"), invoice.status), before)
        self.assertEqual(adjustment.amount_owed, 0)

    def test_a_raising_adjustment_adds_to_what_is_owed(self):
        invoice = self.create_invoice(lines=((5_000_000, 10),))

        self.create_invoice(lines=((300_000, 10),), kind="adjustment", adjusts_id=invoice.id)

        self.assertEqual(invoice.amount_owed, 5_500_000 + 330_000)

    def test_only_a_posted_advance_or_final_invoice_of_the_same_customer_is_corrected(self):
        posted = self.create_invoice()
        draft = self.create_invoice(post=False)
        adjustment = self.create_invoice(lines=((-100_000, 0),), kind="adjustment", adjusts_id=posted.id)
        other = self.env["res.partner"].create({"name": "Nhà máy Nước Bình An"})

        refused = (
            {"kind": "adjustment", "adjusts_id": draft.id},
            {"kind": "adjustment", "adjusts_id": adjustment.id},
            {"kind": "adjustment", "adjusts_id": posted.id, "partner": other},
            {"kind": "final", "adjusts_id": posted.id},
        )
        for vals in refused:
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                partner = vals.pop("partner", None)
                self.create_invoice(lines=((-100_000, 0),), post=False, partner=partner, **vals)

    def test_an_adjustment_cannot_take_the_invoice_below_zero(self):
        invoice = self.create_invoice(lines=((1_000_000, 0),))
        adjustment = self.create_invoice(lines=((-1_500_000, 0),), kind="adjustment", adjusts_id=invoice.id, post=False)

        with self.assertRaises(UserError):
            adjustment.action_post()
        self.assertEqual(invoice.amount_owed, 1_000_000)

    def test_create_adjustment_opens_a_draft_for_the_posted_invoice(self):
        invoice = self.create_invoice()

        action = invoice.action_create_adjustment()
        adjustment = self.env[invoice._name].browse(action["res_id"])

        self.assertEqual((adjustment.kind, adjustment.adjusts_id, adjustment.status), ("adjustment", invoice, "draft"))
        self.assertEqual(adjustment.partner_id, invoice.partner_id)
        with self.assertRaises(UserError):
            adjustment.action_create_adjustment()
