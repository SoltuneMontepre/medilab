from datetime import date, datetime

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SAMPLE_COLLECTION_START
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE
from odoo.addons.sol_laboratory.services.staff_language import staff_env


@tagged("post_install", "-at_install")
@freeze_time("2026-12-07 02:00:00")
class TestCartDetails(OrderCase):
    """The customer says how the samples reach the laboratory; the details are remembered and reach collection staff."""

    def setUp(self):
        super().setUp()
        # 2026-12-07 is a Monday, 09:00 in the laboratory.
        self.env.company.tz = VIETNAM_ZONE

    def test_a_new_order_starts_with_the_last_collection_or_a_pickup_at_the_customer_address(self):
        self.customer.street = "12 Le Loi"
        first = self.make_order([(self.lead_product, 1)])

        first._prefill_collection()

        self.assertEqual((first.collection_method, first.collection_time), ("pickup", "any"))
        self.assertIn("12 Le Loi", first.collection_address or "")

        self.make_order(
            [(self.lead_product, 1)],
            status="submitted",
            collection_method="drop_off",
            collection_time="afternoon",
            collection_note="Gate B",
        )
        second = self.make_order([(self.lead_product, 1)])
        second._prefill_collection()

        self.assertEqual(
            (second.collection_method, second.collection_time, second.collection_note),
            ("drop_off", "afternoon", "Gate B"),
        )

    def test_the_details_keep_only_working_days_within_a_month(self):
        order = self.make_order([(self.lead_product, 1)])

        order._save_portal_collection({"collection_date": "2026-12-12", "collection_method": "teleport"})
        self.assertFalse(order.expected_collection_date)
        self.assertFalse(order.collection_method)

        order._save_portal_collection({"collection_date": "2026-12-08", "collection_time": "morning"})
        self.assertEqual((order.expected_collection_date, order.collection_time), (date(2026, 12, 8), "morning"))

        order._save_portal_collection({"collection_date": "2027-03-01"})
        self.assertEqual(order.expected_collection_date, date(2026, 12, 8))

    def test_submitting_needs_a_collection_and_a_pickup_address(self):
        order = self.make_order([(self.lead_product, 1)])

        with self.assertRaisesRegex(UserError, "Choose how the samples reach the laboratory"):
            order._check_portal_collection()
        order.collection_method = "pickup"
        with self.assertRaisesRegex(UserError, "Give the address"):
            order._check_portal_collection()
        order.collection_method = "drop_off"
        order._check_portal_collection()

    def test_the_results_date_refuses_a_day_off_and_more_than_a_month_ahead(self):
        order = self.make_order([(self.lead_product, 1)])

        with self.assertRaisesRegex(UserError, "does not return results on this day"):
            order._set_portal_dates("2026-12-12")
        with self.assertRaisesRegex(UserError, "Choose a date up to"):
            order._set_portal_dates("2027-02-01")

    def test_the_calendar_offers_working_days_up_to_a_month_ahead(self):
        order = self.make_order([(self.lead_product, 1)])

        days = {day["value"]: day for week in order._requested_date_calendar(False, False)["weeks"] for day in week}

        self.assertFalse(days["2026-12-12"]["open"])
        self.assertTrue(days["2026-12-14"]["open"])
        self.assertNotIn("2027-01-11", days)

    def test_sales_are_warned_of_a_pickup_on_a_company_day_off(self):
        order = self.make_order([(self.lead_product, 1)])

        order.expected_collection_date = date(2026, 12, 12)
        warning = order._onchange_pickup_on_working_day()
        self.assertIn("company day off", (warning or {}).get("warning", {}).get("message", ""))
        order.expected_collection_date = date(2026, 12, 14)
        self.assertIsNone(order._onchange_pickup_on_working_day())

    def test_collection_staff_get_the_customer_s_place_time_and_note(self):
        self.route_collection_to_delivery_staff()
        order = self.make_quotable_order()
        order.write(
            {
                "expected_collection_date": date(2026, 12, 9),
                "collection_method": "pickup",
                "collection_address": "Gate 2, 45 Le Loi",
                "collection_time": "afternoon",
                "collection_note": "Call Ms Lan",
            }
        )
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        wizard = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({})
        )

        self.assertEqual(wizard.address, "Gate 2, 45 Le Loi")
        # 13:00 in the laboratory on the preferred day.
        self.assertEqual(wizard.appointment, datetime(2026, 12, 9, 6, 0))
        wizard.action_start()
        task = self.collection_tasks(order)
        self.assertEqual(task.place, "Gate 2, 45 Le Loi")
        for line in order._collection_preference_lines(staff_env(self.env)):
            self.assertIn(line, task.note or "")
        english = order._collection_preference_lines(self.env(context=dict(self.env.context, lang="en_US")))
        self.assertEqual(english, ["Preferred time: Afternoon", "Customer note: Call Ms Lan"])

    def test_the_collection_dialog_warns_when_the_customer_brings_the_samples(self):
        order = self.make_confirmed_order()
        order.sudo().collection_method = "drop_off"

        wizard = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({"appointment": datetime(2026, 12, 9, 2, 0)})
        )

        self.assertIn("bring the samples to the laboratory", wizard.schedule_warning or "")
