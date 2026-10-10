from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .payos_case import PayosCase
from odoo.addons.commerce.constants.models import MODEL_PAYMENT_LINK_TRANSACTION
from odoo.addons.commerce.constants.xml_ids import REPORT_RECONCILIATION_DAY

# Days no demo record reconciles.
DAY = date(2026, 5, 11)
NEXT_DAY = date(2026, 5, 12)


@tagged("post_install", "-at_install")
class TestReconciliationDay(PayosCase):
    def store_transfer(self, link, reference, amount, when="2026-05-11 10:15:00"):
        # A transfer PayOS reported whose payment was not recorded (as before the payments feature existed).
        return self.env[MODEL_PAYMENT_LINK_TRANSACTION].create(
            {
                "link_id": link.id,
                "reference": reference,
                "amount": amount,
                "transacted_at": link._parse_transaction_time(when),
            }
        )

    def as_accountant(self, records):
        return records.with_user(self.accountant.user_id)

    def report(self, day):
        return self.env["ir.actions.report"]._render_qweb_html(REPORT_RECONCILIATION_DAY, day.ids)[0].decode()

    def test_a_transfer_without_its_payment_is_flagged_and_blocks_the_lock(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, _ = self.create_link(invoice)
        transfer = self.store_transfer(link, "FT1", 5_000_000)
        day = self.open_day(DAY)

        self.assertEqual((day.transaction_ids, day.total_amount, day.blocking_count), (transfer, 5_000_000, 1))
        self.assertEqual(transfer.match_state, "missing_payment")
        with self.assertRaisesRegex(UserError, "no payment recorded"):
            self.as_accountant(day).action_lock()

        with self.assertRaises(AccessError):
            transfer.with_user(self.salesperson.user_id).action_record_payments()
        self.as_accountant(transfer).action_record_payments()

        payment = transfer.payment_id
        self.assertEqual(
            (payment.invoice_id, payment.amount, payment.status, payment.method),
            (invoice, 5_000_000, "confirmed", "online"),
        )
        self.assertEqual((transfer.match_state, day.blocking_count, invoice.payment_status), ("matched", 0, "paid"))
        self.as_accountant(day).action_lock()
        self.assertEqual((day.status, day.locked_by_id), ("locked", self.accountant.user_id))

    def test_record_payments_creates_one_payment_per_missing_transfer_of_the_link(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, _ = self.create_link(invoice)
        first = self.store_transfer(link, "FT1", 2_000_000)
        second = self.store_transfer(link, "FT2", 3_000_000, "2026-05-11 16:00:00")

        self.as_accountant(first).action_record_payments()

        self.assertEqual(len(link.payment_ids), 2)
        self.assertEqual(sorted(link.payment_ids.mapped("amount")), [2_000_000, 3_000_000])
        self.assertEqual((first.payment_id.amount, second.payment_id.amount), (2_000_000, 3_000_000))
        self.assertEqual(sum(link.payment_ids.mapped("amount")), link.amount_paid)

    def test_an_underpaid_link_and_an_overpaying_payment_need_an_acknowledgement_with_a_reason(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        underpaid, _ = self.create_link(invoice, amount=3_000_000)
        self.notify(underpaid, 1_000_000, "FT1")
        other = self.create_invoice(lines=((1_000_000, 0),))
        overpaid, fake = self.create_link(other, amount=1_000_000)
        fake.answers = {}
        self.pay(other, 1_000_000)
        self.notify(overpaid, 1_000_000, "FT2", when="2026-05-11 11:00:00")
        day = self.open_day(DAY)

        states = {transaction.reference: transaction.match_state for transaction in day.transaction_ids}
        self.assertEqual(states, {"FT1": "underpaid", "FT2": "overpaying"})
        self.assertEqual((day.blocking_count, day.unacknowledged_count), (0, 2))
        with self.assertRaisesRegex(UserError, "to be acknowledged"):
            self.as_accountant(day).action_lock()
        with self.assertRaisesRegex(UserError, "reason"):
            self.as_accountant(underpaid).action_acknowledge()
        with self.assertRaises(AccessError):
            underpaid.with_user(self.salesperson.user_id).action_acknowledge()

        self.as_accountant(underpaid).write({"acknowledgement_reason": "Customer pays the rest next week"})
        self.as_accountant(underpaid).action_acknowledge()
        overpaying = overpaid.payment_ids
        self.as_accountant(overpaying).write({"acknowledgement_reason": "Refunded by bank transfer"})
        self.as_accountant(overpaying).action_acknowledge()

        self.assertEqual(day.unacknowledged_count, 0)
        self.as_accountant(day).action_lock()
        html = self.report(day)
        for text in (
            "Customer pays the rest next week",
            "Refunded by bank transfer",
            self.accountant.name,
            "Underpaid",
            "Overpaying",
        ):
            self.assertIn(text, html)

    def test_a_later_partial_transfer_needs_a_new_acknowledgement_on_its_own_day(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, _ = self.create_link(invoice, amount=3_000_000)
        self.notify(link, 1_000_000, "FT1")
        first_day = self.open_day(DAY)
        self.as_accountant(link).write({"acknowledgement_reason": "Instalments agreed"})
        self.as_accountant(link).action_acknowledge()
        self.as_accountant(first_day).action_lock()

        self.notify(link, 1_000_000, "FT2", when="2026-05-12 09:00:00")
        second_day = self.open_day(NEXT_DAY)

        self.assertFalse(link.is_acknowledged)
        self.assertEqual((second_day.unacknowledged_count, first_day.status), (1, "locked"))
        with self.assertRaisesRegex(UserError, "to be acknowledged"):
            self.as_accountant(second_day).action_lock()
        self.as_accountant(link).write({"acknowledgement_reason": "Still instalments"})
        self.as_accountant(link).action_acknowledge()
        self.as_accountant(second_day).action_lock()
        self.assertEqual(second_day.status, "locked")

    def test_a_later_overpayment_on_another_link_never_changes_a_locked_row(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link_a, _ = self.create_link(invoice, amount=5_000_000)
        self.notify(link_a, 5_000_000, "FT1")
        first_day = self.open_day(DAY)
        self.as_accountant(first_day).action_lock()
        before = self.report(first_day)

        # A second link on the same invoice, as the portal creates one for a partial amount.
        link_b = self.env["medilab.payment.link"].create(
            {"invoice_id": invoice.id, "amount": 1_000_000, "status": "pending", "expires_at": "2099-01-01 00:00:00"}
        )
        self.notify(link_b, 1_000_000, "FT2", when="2026-05-12 09:00:00")

        self.assertEqual((link_a.payment_ids.is_overpaying, link_b.payment_ids.is_overpaying), (False, True))
        self.assertEqual(link_a.transaction_ids.match_state, "matched")
        self.assertEqual(self.report(first_day), before)
        self.assertEqual(self.open_day(NEXT_DAY).transaction_ids.match_state, "overpaying")

    def test_a_locked_day_freezes_its_online_payments_but_payos_may_still_report(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, _ = self.create_link(invoice, amount=5_000_000)
        self.notify(link, 2_000_000, "FT1")
        cash = self.pay(invoice, 500_000, user=self.salesperson, payment_date=DAY)
        day = self.open_day(DAY)
        self.as_accountant(link).write({"acknowledgement_reason": "Rest to come"})
        self.as_accountant(link).action_acknowledge()
        self.as_accountant(day).action_lock()
        online = link.payment_ids
        transfer = link.transaction_ids

        refused = (
            lambda: self.as_accountant(online).write({"acknowledgement_reason": "x"}),
            lambda: online.sudo().write({"amount": 1}),
            lambda: transfer.sudo().write({"amount": 1}),
            lambda: transfer.sudo().unlink(),
            lambda: link.sudo().write({"status": "cancelled"}),
            lambda: self.as_accountant(day).write({"day": NEXT_DAY}),
            lambda: day.sudo().unlink(),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaisesRegex(UserError, "locked"):
                action()
        self.as_accountant(cash).write({"amount": 600_000})
        self.assertEqual(cash.amount, 600_000)

        self.notify(link, 3_000_000, "FT2", when="2026-05-11 23:30:00")

        late = link.payment_ids - online
        self.assertEqual((len(late), late.recorded_after_lock, late.is_day_locked), (1, True, True))
        self.assertEqual((link.status, link.amount_paid), ("paid", 5_000_000))
        self.assertIn("recorded after the lock", self.report(day))
        self.assertIn("5.000.000", self.report(day).replace("\xa0", " ").replace("5,000,000", "5.000.000"))
