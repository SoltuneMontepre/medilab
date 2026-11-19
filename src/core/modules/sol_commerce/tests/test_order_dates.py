from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.models.sample_collection.test_request_estimate import TestRequestEstimate


@tagged("post_install", "-at_install")
class TestOrderDates(OrderCase):
    """Lead and Cadmium are tested in 5 working days; Lead also by a subcontractor in 8."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter.method_ids.turnaround_days = 5
        cls.other.method_ids.turnaround_days = 5

    def test_the_turnaround_is_the_longest_of_the_order_s_ways(self):
        self.other.method_ids.turnaround_days = 7

        order = self.make_quotable_order([(self.lead_product, 1), (self.package_product, 1)])

        self.assertEqual(order.turnaround_days, 7)
        estimate = order.estimated_result_date
        assert isinstance(estimate, date)
        self.assertGreater(estimate, date.today())

    def test_a_way_without_a_turnaround_keeps_the_quotation_from_being_sent(self):
        self.parameter.method_ids.turnaround_days = 0
        order = self.make_quotable_order()

        self.assertTrue(order.turnaround_missing)
        with self.assertRaisesRegex(UserError, "Set the standard turnaround"):
            order.with_user(self.sales).action_send_quotation()

    def test_a_requested_date_the_turnaround_meets_becomes_the_committed_date(self):
        order = self.make_quotable_order()
        requested = date.today() + timedelta(days=60)
        order.requested_date = requested

        order.with_user(self.sales).action_send_quotation()

        self.assertEqual(order.committed_date, requested)

    def test_an_earlier_requested_date_leaves_the_date_to_sample_receipt(self):
        order = self.make_quotable_order()
        order.requested_date = date.today()

        order.with_user(self.sales).action_send_quotation()

        self.assertFalse(order.committed_date)

    def test_a_committed_date_earlier_than_the_turnaround_allows_is_refused(self):
        order = self.make_quotable_order()
        order.committed_date = date.today()

        with self.assertRaisesRegex(UserError, "earlier than the standard turnaround"):
            order.with_user(self.sales).action_send_quotation()

    def test_a_priority_request_must_be_decided_before_sending(self):
        order = self.make_quotable_order()
        order._set_portal_dates((date.today() + timedelta(days=2)).isoformat(), True)

        with self.assertRaisesRegex(UserError, "Accept or decline"):
            order.with_user(self.sales).action_send_quotation()

        order.with_user(self.sales).action_decline_priority()
        order.with_user(self.sales).action_send_quotation()
        self.assertFalse(order.priority)

    def test_priority_needs_a_requested_date(self):
        order = self.make_order([(self.lead_product, 1)])

        with self.assertRaisesRegex(UserError, "Give the date"):
            order._set_portal_dates(False, True)

    def test_an_infeasible_priority_request_is_refused_with_the_earliest_date(self):
        order = self.make_quotable_order()
        requested = date.today() + timedelta(days=1)
        order.write({"requested_date": requested, "priority_request": "requested"})
        earliest = date.today() + timedelta(days=9)

        with (
            patch.object(
                TestRequestEstimate,
                "_check_priority",
                return_value={"date": earliest, "feasible": False, "reasons": []},
            ),
            self.assertRaisesRegex(UserError, "earliest feasible date is"),
        ):
            order.with_user(self.sales).action_accept_priority()
        self.assertEqual(order.priority_request, "requested")

    def test_an_accepted_priority_commits_the_requested_date_and_makes_the_tests_urgent(self):
        order = self.make_quotable_order()
        requested = date.today() + timedelta(days=3)
        order.write({"requested_date": requested, "priority_request": "requested"})

        with patch.object(
            TestRequestEstimate,
            "_check_priority",
            return_value={"date": requested, "feasible": True, "reasons": []},
        ):
            order.with_user(self.sales).action_accept_priority()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        request = order.sudo().test_request_id
        self.assertTrue(order.priority)
        self.assertEqual(order.committed_date, requested)
        self.assertTrue(request.priority)
        self.assertEqual(request.committed_date, requested)
        self.assertEqual(set(request.sample_ids.test_ids.mapped("priority")), {"urgent"})

    def test_the_dates_stop_changing_once_the_quotation_is_sent(self):
        order = self.sent_order()

        with self.assertRaisesRegex(UserError, "Revise the quotation"):
            order.with_user(self.sales).requested_date = date.today()

    def test_the_test_request_takes_the_dates_and_turnaround(self):
        order = self.make_quotable_order()
        order.requested_date = date.today() + timedelta(days=60)
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)

        order.with_user(self.sales).action_confirm_order()

        request = order.sudo().test_request_id
        self.assertEqual(request.requested_date, order.requested_date)
        self.assertEqual(request.committed_date, order.requested_date)
        self.assertEqual(request.turnaround_days, 5)

    def test_the_priority_check_reserves_nothing_and_needs_a_subcontract_turnaround(self):
        subcontracted = (
            self.env[MODEL_PARAMETER_METHOD]
            .search([("parameter_id", "=", self.parameter.id)], limit=1)
            .copy(
                {
                    "department_id": False,
                    "subcontractor_id": self.env["medilab.subcontractor"]
                    .create({"name": "Northern Testing Laboratory"})
                    .id,
                    "turnaround_days": 0,
                }
            )
        )
        bookings = self.env["medilab.machine.booking"].search_count([])

        check = self.env[MODEL_TEST_REQUEST]._check_priority(self.pair | subcontracted, date.today())

        self.assertFalse(check["feasible"])
        self.assertTrue(any("has no turnaround" in reason for reason in check["reasons"]))
        self.assertEqual(self.env["medilab.machine.booking"].search_count([]), bookings)
