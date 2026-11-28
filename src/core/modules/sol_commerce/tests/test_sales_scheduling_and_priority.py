from datetime import date, datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time
from lxml import etree

from odoo import fields
from odoo.tools import html2plaintext
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged
from odoo.tests.form import O2MProxy

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ORDER_SAMPLE,
    MODEL_SALE_ORDER,
    MODEL_SAMPLE_COLLECTION_START,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TYPE,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE, SAMPLE_TEST_CODE
from odoo.addons.sol_laboratory.models.sample_collection.test_request_estimate import TestRequestEstimate
from odoo.addons.sol_laboratory.services.staff_language import staff_env
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestSalesSchedulingAndPriority(OrderCase):
    """Covers priority badges/ordering, reactive line & date scheduling, collection dialog warnings, and task access."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter.method_ids.turnaround_days = 5
        cls.other.method_ids.turnaround_days = 5

    def after(self, day, days):
        return self.env[MODEL_TEST_REQUEST]._date_after_working_days(day, days)

    def today(self):
        return fields.Date.context_today(self.env.user)

    def make_priority_order(self):
        order = self.make_quotable_order()
        pickup = self.after(self.today(), 2)
        order.write({"expected_collection_date": pickup, "requested_date": self.after(pickup, 2)})
        return order

    def accept(self, order):
        with patch.object(
            TestRequestEstimate,
            "_check_priority",
            return_value={"date": order.requested_date, "feasible": True, "reasons": []},
        ):
            order.with_user(self.sales).action_accept_priority()

    def test_priority_badge_attention_flag_and_list_ordering(self):
        standard = self.make_quotable_order()
        requested = self.make_priority_order()
        declined = self.make_priority_order()
        declined.with_user(self.sales).action_decline_priority()
        accepted = self.make_priority_order()
        self.accept(accepted)

        self.assertEqual((standard.priority_badge, standard.is_priority_attention), ("standard", False))
        self.assertEqual((requested.priority_badge, requested.is_priority_attention), ("requested", True))
        self.assertEqual((declined.priority_badge, declined.is_priority_attention), ("declined", False))
        self.assertEqual((accepted.priority_badge, accepted.is_priority_attention), ("priority", True))

        searched = self.env[MODEL_SALE_ORDER].search([("id", "in", (standard | declined | requested | accepted).ids)])
        self.assertEqual(set(searched[:2].ids), {requested.id, accepted.id})
        self.assertEqual(set(searched[2:].ids), {standard.id, declined.id})

    def test_order_form_hides_customer_lead_autofills_sample_type_updates_dates_and_shows_expected_samples(self):
        form_view = self.env.ref("sol_commerce.view_order_form_medilab")
        form_arch = etree.fromstring(self.env[MODEL_SALE_ORDER].get_view(form_view.id, "form")["arch"])
        self.assertFalse(form_arch.xpath(".//field[@name='customer_lead']"))
        self.assertFalse(form_arch.xpath(".//field[@name='turnaround_days']"))
        self.assertFalse(form_arch.xpath(".//field[@name='standard_return_date']"))
        self.assertFalse(form_arch.xpath(".//list//field[@name='tax_ids'][not(@column_invisible)]"))

        surface_water = self.env[MODEL_SAMPLE_TYPE].create({"name": "Surface water", "code": "LM-ORD-SURF"})
        self.offer(self.parameter, surface_water)
        self.offer(self.other, surface_water)
        self.env.company.tz = VIETNAM_ZONE

        first_day = self.after(self.today(), 1)
        later_day = self.after(first_day, 2)
        with Form(self.env[MODEL_SALE_ORDER].with_context(medilab_sales_order=True)) as form:
            form.customer_id = self.customer
            form.expected_collection_date = first_day
            lines = assert_instance(form.product_line_ids, O2MProxy)
            with lines.new() as line:
                line.product_template_id = self.lead_product
                line.sample_type_id = surface_water
            # Adding a second line (here a package supporting surface_water) inherits the unique existing sample type.
            with lines.new() as line:
                line.product_template_id = self.package_product
                self.assertEqual(line.sample_type_id, surface_water)
            initial_committed = form.committed_date
            self.assertEqual(initial_committed, self.after(first_day, 5))

            form.expected_collection_date = later_day
            self.assertEqual(form.committed_date, self.after(later_day, 5))
            order = form.save()

        self.assertEqual(order._catalog_lines().sample_type_id, surface_water)
        order.write({"advance_method": "cash", "advance_mode": "full", "user_id": self.sales.id})
        order._catalog_lines().sample_id = self.env[MODEL_ORDER_SAMPLE].create(
            {
                "order_id": order.id,
                "customer_sample_name": "Surface Sample A",
                "sample_type_id": surface_water.id,
                "physical_state": "liquid",
            }
        )
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.test_request_id.status, "confirmed")
        self.assertIn("Surface Sample A", order.collected_samples_html or "")
        self.assertIn("Expected", order.collected_samples_html or "")

    @freeze_time("2026-12-07 02:00:00")
    def test_collection_wizard_warnings_duration_notes_and_sales_schedule_access(self):
        # 2026-12-07 is a Monday; set Vietnam timezone (UTC+7 -> 09:00 local).
        self.env.company.tz = VIETNAM_ZONE
        self.contact.phone = "+84909111222"
        staff = self.route_collection_to_delivery_staff()
        staff.employee_id.tz = VIETNAM_ZONE
        order = self.make_quotable_order()
        order.write(
            {
                "expected_collection_date": date(2026, 12, 9),
                "advance_mode": "percentage",
                "advance_value": 30,
                "balance_due": "at_collection",
            }
        )
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        monday_morning = datetime(2026, 12, 7, 3, 0)  # 10:00 local Monday
        sunday_morning = datetime(2026, 12, 13, 3, 0)  # 10:00 local Sunday (day off)

        # Past warning
        past_appointment = monday_morning - timedelta(hours=2)
        past_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({"appointment": past_appointment})
        )
        self.assertEqual(past_wiz.duration_minutes, 60)
        self.assertEqual(past_wiz.appointment_end, past_appointment + timedelta(minutes=60))
        self.assertIn("past", past_wiz.schedule_warning or "")
        self.assertIn("Pham Thi Hoa", past_wiz.contact_summary or "")
        self.assertIn("+84909111222", past_wiz.contact_summary or "")
        self.assertIn("Lavie bottled water 1 L", past_wiz.samples_summary_html or "")
        self.assertIn("Balance due", past_wiz.balance_notice or "")

        # Day-off + late turnaround warning
        off_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({"appointment": sunday_morning + timedelta(days=7)})
        )
        self.assertIn("outside standard working hours", off_wiz.schedule_warning or "")
        self.assertIn("after the expected return date", off_wiz.schedule_warning or "")

        # Invalid duration <= 0 raises on confirm
        bad_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({"appointment": monday_morning, "duration_minutes": 0})
        )
        with self.assertRaisesRegex(UserError, "above 0 minutes"):
            bad_wiz.action_start()

        # Assign a task to the sole delivery staff to trigger busy / travel-buffer warning, plus an unclaimed overlap.
        collection_type = self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        busy_order = self.make_confirmed_order()
        self.env[MODEL_TASK].sudo().create(
            {
                "type_id": collection_type.id,
                "name": "Existing assigned collection",
                "document_model": MODEL_TEST_REQUEST,
                "document_id": busy_order.test_request_id.id,
                "assignee_id": staff.id,
                "status": "assigned",
                "planned_start": monday_morning,
                "planned_end": monday_morning + timedelta(minutes=60),
                "deadline": monday_morning + timedelta(hours=2),
            }
        )
        busy_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({"appointment": monday_morning + timedelta(minutes=75)})
        )
        self.assertIn("All sample delivery staff are busy or off", busy_wiz.schedule_warning or "")

        # Confirm on a clean Tuesday morning with custom 90-minute duration.
        tuesday_morning = datetime(2026, 12, 8, 2, 0)  # 09:00 local Tuesday
        good_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create(
                {
                    "appointment": tuesday_morning,
                    "duration_minutes": 90,
                    "address": "Gate B, 99 Pasteur",
                }
            )
        )
        self.assertEqual(good_wiz.staff_availability, staff.name)
        good_wiz.action_start()

        created_task = self.collection_tasks(order)
        self.assertEqual(created_task.planned_end, tuesday_morning + timedelta(minutes=90))
        self.assertEqual(created_task.location_display, "Gate B, 99 Pasteur")
        self.assertIn("Pham Thi Hoa", created_task.note or "")
        self.assertIn(order._collection_balance_line(staff_env(self.env)), created_task.note or "")

        # Add an unclaimed overlap on a second available order at the same Tuesday window (1 available staff, 1 open).
        order2 = self.make_confirmed_order()
        overlap_wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order2.id)
            .create({"appointment": tuesday_morning})
        )
        self.assertIn("unclaimed collection(s) already overlap", overlap_wiz.schedule_warning or "")

        # Claiming creates the collector's calendar event carrying the note, place and link to the test request.
        created_task.with_user(staff.user_id).action_claim()
        event = self.env["calendar.event"].sudo().search([("medilab_task_id", "=", created_task.id)])
        for line in (created_task.note or "").splitlines():
            self.assertIn(line, html2plaintext(event.description))
        self.assertEqual(event.location, "Gate B, 99 Pasteur")
        self.assertEqual(event.res_model, MODEL_TEST_REQUEST)
        self.assertEqual(event.res_id, order.test_request_id.id)

        # Verify Sales cannot read collection or testing tasks.
        testing_type = self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_TEST_CODE)], limit=1)
        testing_task = (
            self.env[MODEL_TASK]
            .sudo()
            .create(
                {
                    "type_id": testing_type.id,
                    "name": "Lab testing task",
                    "document_model": MODEL_TEST_REQUEST,
                    "document_id": order.test_request_id.id,
                    "assignee_id": staff.id,
                    "status": "assigned",
                    "deadline": tuesday_morning + timedelta(days=1),
                }
            )
        )
        self.assertFalse(
            self.env[MODEL_TASK].with_user(self.sales).search([("id", "in", [created_task.id, testing_task.id])])
        )
        with self.assertRaises(AccessError):
            created_task.with_user(self.sales).read(["name"])
        with self.assertRaises(AccessError):
            testing_task.with_user(self.sales).read(["name"])

    @freeze_time("2026-11-28 00:00:00")
    def test_sunday_expected_collection_defaults_to_monday_morning_within_committed_date(self):
        self.env.company.tz = VIETNAM_ZONE
        self.route_collection_to_delivery_staff()
        order = self.make_quotable_order()
        order.write(
            {"expected_collection_date": date(2026, 11, 29), "advance_method": "none", "balance_due": "before_report"}
        )
        order.with_user(self.head).action_send_quotation()
        order._latest_quotation()._accept()
        order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.committed_date, date(2026, 12, 4))
        wiz = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .create({})
        )
        self.assertEqual(wiz.appointment, datetime(2026, 11, 30, 1, 0))
        self.assertNotIn("expected return date", wiz.schedule_warning or "")
        wiz.action_start()
        self.assertTrue(self.collection_tasks(order))
