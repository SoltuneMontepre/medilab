from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE


@tagged("post_install", "-at_install")
class TestCollectionAppointment(OrderCase):
    """Sales agrees a collection appointment that is still to come and lets the turnaround meet the committed date;
    sample delivery staff take collections the travel buffer apart; Sales hears when a test is at risk."""

    def test_an_appointment_in_the_past_is_refused(self):
        self.route_collection_to_delivery_staff()
        order = self.make_confirmed_order()

        with self.assertRaisesRegex(UserError, "still to come"):
            order.with_user(self.sales).action_start_sample_collection(
                appointment=fields.Datetime.now() - timedelta(hours=1)
            )

    def test_an_appointment_too_late_for_the_committed_date_is_refused(self):
        self.route_collection_to_delivery_staff()
        self.parameter.method_ids.turnaround_days = 5
        order = self.make_confirmed_order()
        appointment = fields.Datetime.now() + timedelta(days=1)
        order.sudo().with_context(**{CHANGING_COMMITTED_DATE: True}).committed_date = fields.Date.today() + timedelta(
            days=1
        )

        with self.assertRaisesRegex(UserError, "after the expected return date"):
            order.with_user(self.sales).action_start_sample_collection(appointment=appointment)

    def test_staff_cannot_take_two_collections_closer_than_the_travel_buffer(self):
        staff = self.route_collection_to_delivery_staff()
        first, second = self.make_confirmed_order(), self.make_confirmed_order()
        appointment = fields.Datetime.now() + timedelta(days=1)
        first.with_user(self.sales).action_start_sample_collection(appointment=appointment)
        second.with_user(self.sales).action_start_sample_collection(appointment=appointment + timedelta(minutes=90))
        self.collection_tasks(first).with_user(staff.user_id).action_claim()

        with self.assertRaisesRegex(ValidationError, "too close"):
            self.collection_tasks(second).with_user(staff.user_id).action_claim()

    def test_collections_the_travel_buffer_apart_after_duration_can_both_be_taken(self):
        staff = self.route_collection_to_delivery_staff()
        first, second = self.make_confirmed_order(), self.make_confirmed_order()
        appointment = fields.Datetime.now() + timedelta(days=1)
        first.with_user(self.sales).action_start_sample_collection(appointment=appointment)
        second.with_user(self.sales).action_start_sample_collection(appointment=appointment + timedelta(minutes=120))
        self.collection_tasks(first).with_user(staff.user_id).action_claim()

        self.collection_tasks(second).with_user(staff.user_id).action_claim()

        self.assertEqual(self.collection_tasks(second).assignee_id, staff)

    def test_the_salesperson_hears_when_a_test_is_at_risk(self):
        order = self.make_confirmed_order()
        request = order.test_request_id
        request.sudo().with_context(**{CHANGING_COMMITTED_DATE: True}).committed_date = fields.Date.today() + timedelta(
            days=3
        )

        request.sample_ids.test_ids._flag_at_risk()

        notice = order.message_ids.filtered(lambda message: "at risk" in (message.body or ""))
        self.assertTrue(notice)
        self.assertEqual(notice.partner_ids, self.sales.partner_id)
