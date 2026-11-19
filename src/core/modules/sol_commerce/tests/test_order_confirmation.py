from pathlib import Path

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import load_script
from odoo.tests import Form, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_CUSTOMER_SALES_TERMS, MODEL_SAMPLE_COLLECTION_START
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST

CREDIT_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.16.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestOrderConfirmation(OrderCase):
    def accepted_unpaid_order(self, lines=None):
        order = self.make_quotable_order(lines)
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        order._latest_quotation()._accept()
        order.with_user(self.sales).action_confirm_order()
        return order

    def test_confirming_creates_the_test_request_from_the_samples(self):
        order = self.make_quotable_order([(self.lead_product, 2), (self.package_product, 1)])
        samples = order.sample_ids
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)

        order.with_user(self.sales).action_confirm_order()

        request = order.test_request_id
        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(request.customer_id, self.customer_record)
        self.assertEqual(request.report_recipient_id, self.contact)
        self.assertEqual(len(request.sample_ids), len(samples))
        tests = request.sample_ids.test_ids
        self.assertEqual(
            sorted(test.parameter_id.id for test in tests), sorted([self.parameter.id] * 2 + [self.other.id])
        )
        self.assertEqual(sum(tests.filtered(lambda test: test.parameter_id == self.parameter).mapped("quantity")), 3)
        self.assertEqual(request.sample_ids.customer_sample_name, samples.customer_sample_name)

    def test_a_quotation_must_be_accepted_before_confirming(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")
        self.assertFalse(order.test_request_id)

    def test_an_order_without_a_quotation_cannot_be_confirmed(self):
        order = self.make_quotable_order()

        with self.assertRaises(UserError) as error:
            order.with_user(self.sales).action_confirm_order()

        self.assertIn("accept the quotation", str(error.exception))

    def test_a_replaced_revision_cannot_be_confirmed(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        first = order._latest_quotation()
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(first.status, "replaced")

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")
        self.assertFalse(order.test_request_id)

    def test_the_standard_confirm_button_runs_the_same_checks(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm()

        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(order.state, "sale")
        self.assertTrue(order.test_request_id)

    def test_the_confirm_context_key_cannot_skip_the_checks(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        for context in ({"medilab_odoo_confirm": True}, {"medilab_confirming_order_ids": [order.id]}):
            with self.assertRaises(UserError):
                order.with_user(self.sales).with_context(**context).action_confirm()

        self.assertEqual(order.order_status, "claimed")
        self.assertEqual(order.state, "sent")
        self.assertFalse(order.test_request_id)

    def test_sample_collection_starts_once_the_order_is_confirmed(self):
        self.route_collection_to_delivery_staff()
        order = self.sent_order()
        self.pay_advance(order)

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_start_sample_collection()
        order.with_user(self.sales).action_confirm_order()

        self.assertTrue(order.confirmed_at)
        action = order.with_user(self.sales).action_start_sample_collection()
        self.assertEqual(action["tag"], "display_notification")

    def test_starting_collection_queues_one_task_for_sample_delivery_staff(self):
        staff = self.route_collection_to_delivery_staff()
        self.customer.write({"street": "12 Nguyen Hue", "city": "Ho Chi Minh"})
        order = self.make_confirmed_order()

        order.with_user(self.sales).action_start_sample_collection()

        task = self.collection_tasks(order)
        self.assertEqual(len(task), 1)
        self.assertEqual(task.type_id, self.collection_type())
        self.assertEqual(task.status, "open")
        self.assertFalse(task.assignee_id)
        self.assertFalse(task.department_id)
        self.assertFalse(task.planned_start)
        self.assertIn(order.name, task.name or "")
        self.assertIn("12 Nguyen Hue", task.note or "")
        self.assertTrue(task._claimable_by(staff))
        self.assertFalse(task._claimable_by(self.sales_person))
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_start_sample_collection()
        self.assertEqual(len(self.collection_tasks(order)), 1)

    def test_sales_enters_the_appointment_and_place_of_collection(self):
        self.route_collection_to_delivery_staff()
        self.customer.write({"street": "12 Nguyen Hue", "city": "Ho Chi Minh"})
        order = self.make_confirmed_order()
        form = Form(
            self.env[MODEL_SAMPLE_COLLECTION_START].with_user(self.sales).with_context(default_order_id=order.id)
        )
        self.assertIn("12 Nguyen Hue", str(form.address))
        form.appointment = "2099-12-31 02:00:00"
        form.address = "Gate 3, 45 Le Loi"

        form.save().action_start()

        task = self.collection_tasks(order)
        self.assertEqual(fields.Datetime.to_string(task.deadline), "2099-12-31 02:00:00")
        self.assertEqual(task.note, "Gate 3, 45 Le Loi")
        self.assertTrue(order.has_open_collection)

    def test_a_finished_collection_task_lets_sales_start_another(self):
        self.route_collection_to_delivery_staff()
        order = self.make_confirmed_order()
        order.with_user(self.sales).action_start_sample_collection()
        self.collection_tasks(order).write({"status": "cancelled"})

        order.with_user(self.sales).action_start_sample_collection()

        self.assertEqual(sorted(self.collection_tasks(order).mapped("status")), ["cancelled", "open"])

    def test_only_those_who_change_the_order_start_its_collection(self):
        self.route_collection_to_delivery_staff()
        order = self.make_confirmed_order()

        with self.assertRaises(AccessError):
            order.with_user(self.portal).action_start_sample_collection()
        self.assertFalse(self.collection_tasks(order))

    def test_collection_needs_its_task_type_routed_to_a_role(self):
        order = self.make_confirmed_order()
        self.collection_type().write({"route": "person"})

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_start_sample_collection()
        self.assertFalse(self.collection_tasks(order))

    def test_an_order_is_confirmed_once(self):
        order = self.make_confirmed_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

    def test_confirming_an_order_sent_without_an_advance_lets_its_samples_be_collected(self):
        order = self.accepted_unpaid_order()

        self.assertEqual(order.order_status, "confirmed")
        self.assertTrue(order.test_request_id)
        self.assertFalse(order.show_unpaid_warning)

    def test_confirming_needs_the_customer_record(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.customer_id = self.env["res.partner"].create({"name": "Cong ty chua la khach hang"})

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")

    def test_an_unpaid_balance_does_not_hold_collection_or_reception(self):
        order = self.accepted_unpaid_order()
        request = order.test_request_id
        self.assertEqual(order.payment_request_id.kind, "balance")
        self.assertEqual(request.status, "paid")
        self.assertFalse(order.show_unpaid_warning)

        request.sample_ids.action_receive(1, "unusable", "The bottle leaked")

        self.assertEqual(request.sample_ids.status, "rejected")

    def test_an_unverified_advance_holds_collection_and_reception(self):
        order = self.accepted_unpaid_order()
        quotation = order._latest_quotation()
        self.env["medilab.payment.request"].create(
            {"kind": "advance", "order_id": order.id, "quotation_id": quotation.id, "amount": 100_000}
        )
        order.invalidate_recordset(["show_unpaid_warning"])

        self.assertTrue(order.show_unpaid_warning)
        with self.assertRaisesRegex(UserError, "Verify the order's advance"):
            order.with_user(self.sales).action_start_sample_collection()
        with self.assertRaisesRegex(UserError, "Verify the order's advance"):
            order.test_request_id.sample_ids.action_receive(1, "unusable", "The bottle leaked")

    def test_upgrading_backfills_eligible_legacy_credit_orders(self):
        self.env[MODEL_CUSTOMER_SALES_TERMS].create({"customer_id": self.customer_record.id, "allow_credit": True})
        legacy = self.accepted_unpaid_order()
        legacy.on_credit = False
        legacy.test_request_id.status = "paid"

        advance = self.make_confirmed_order()
        draft = self.make_quotable_order()
        draft.advance_method = "none"

        self.env.flush_all()
        migrate = load_script(str(CREDIT_MIGRATION), "order_credit_post").migrate
        migrate(self.env.cr, "20.0.1.15.0")
        self.env.invalidate_all()

        self.assertTrue(legacy.on_credit)
        self.assertEqual(legacy.test_request_id.status, "on_credit")
        self.assertFalse(advance.on_credit)
        self.assertFalse(draft.on_credit)

        legacy.test_request_id.status = "completed"
        self.assertTrue(legacy.create_final_invoice())

    def test_a_paid_order_and_a_request_without_an_order_are_not_blocked(self):
        paid = self.make_confirmed_order()
        alone = self.env[MODEL_TEST_REQUEST].create({"customer_id": self.customer_record.id})

        self.assertFalse(paid.test_request_id._credit_blocks_confirmation())
        self.assertFalse(alone._credit_blocks_confirmation())

    def test_the_request_of_a_paid_order_is_paid_on_confirmation(self):
        # Confirming the order confirms its request, which is paid already.
        request = self.make_confirmed_order().test_request_id

        self.assertEqual(request.status, "paid")
        request.sample_ids[:1].with_user(self.sales).sudo().action_receive(1, "good")
        self.assertEqual(request.status, "sample_received")

    def test_credit_order_invoices_after_testing_without_marking_test_request_paid(self):
        self.env[MODEL_CUSTOMER_SALES_TERMS].create({"customer_id": self.customer_record.id, "allow_credit": True})
        order = self.accepted_unpaid_order()
        request = order.test_request_id
        self.assertFalse(order.payment_request_id)
        self.assertEqual(request.status, "on_credit")
        self.assertEqual(order.payment_status, "not_paid")
        self.route_collection_to_delivery_staff()
        order.with_user(self.sales).action_start_sample_collection()
        with self.assertRaises(UserError):
            order.create_final_invoice()

        request.status = "completed"
        invoice = order.create_final_invoice()
        invoice.action_post()
        self.env["account.payment"].create_pending_payment(invoice, invoice.amount_residual, "cash").action_post()

        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(request.status, "completed")

    def test_only_the_head_of_sales_changes_the_sales_terms(self):
        terms = self.env[MODEL_CUSTOMER_SALES_TERMS]

        with self.assertRaises(AccessError):
            terms.with_user(self.sales).create({"customer_id": self.customer_record.id, "allow_credit": True})
        created = terms.with_user(self.head).create({"customer_id": self.customer_record.id})
        with self.assertRaises(AccessError):
            created.with_user(self.sales).allow_credit = True

        created.with_user(self.head).allow_credit = True

        self.assertTrue(created.allow_credit)
        self.assertFalse(created.search([("customer_id", "=", self.customer_record.id), ("allow_credit", "=", False)]))

    def test_the_request_of_a_paid_order_is_confirmed_at_once(self):
        order = self.make_confirmed_order()

        self.assertTrue(order.test_request_id.from_order)
        self.assertNotEqual(order.test_request_id.status, "draft")

    def test_the_samples_keep_what_the_customer_agreed_on_the_order(self):
        order = self.make_confirmed_order()
        sample = order.test_request_id.sample_ids[:1]

        with self.assertRaisesRegex(UserError, "revised quotation"):
            sample.with_user(self.sales).customer_sample_name = "Another bottle"
        sample.storage_location = "Fridge 2"

        self.assertEqual(sample.storage_location, "Fridge 2")

    def test_receiving_the_last_expected_sample_finishes_the_collection(self):
        self.route_collection_to_delivery_staff()
        order = self.make_confirmed_order()
        order.with_user(self.sales).action_start_sample_collection()
        samples = order.test_request_id.sample_ids
        samples.physical_state = "liquid"

        samples.with_user(self.sales).sudo().action_receive("1 bottle of 1 L", "good")

        self.assertEqual(self.collection_tasks(order).status, "done")
        self.assertFalse(order.has_open_collection)
