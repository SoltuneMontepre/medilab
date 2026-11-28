from datetime import datetime, timedelta

from lxml import etree

from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestTestRequestPriorityAndCollection(RequestCase):
    """Test requests stay decoupled from Sales, compute turnaround and priority automatically, and show their collection."""

    def test_request_has_no_sales_statuses_and_hides_order_number(self):
        statuses = dict(self.env[MODEL_TEST_REQUEST]._fields["status"]._description_selection(self.env))
        self.assertNotIn("paid", statuses)
        self.assertNotIn("on_credit", statuses)

        form_view = self.env.ref("sol_laboratory.view_medilab_test_request_form")
        search_view = self.env.ref("sol_laboratory.view_medilab_test_request_search")
        form_arch = etree.fromstring(self.env[MODEL_TEST_REQUEST].get_view(form_view.id, "form")["arch"])
        search_arch = etree.fromstring(self.env[MODEL_TEST_REQUEST].get_view(search_view.id, "search")["arch"])

        self.assertFalse(form_arch.xpath(".//field[@name='order_number']"))
        self.assertFalse(search_arch.xpath(".//field[@name='order_number']"))
        self.assertTrue(form_arch.xpath(".//button[@name='action_open_collection_tasks']"))
        self.assertTrue(form_arch.xpath(".//field[@name='collection_appointment_display']"))

    def test_standalone_request_auto_computes_turnaround_priority_and_sorts_first(self):
        self.parameter.method_ids.turnaround_days = 5
        requests = self.env[MODEL_TEST_REQUEST]
        standard = self.create_request()
        expected_standard_date = requests._date_after_working_days(standard.request_date, 5)
        self.assertEqual(standard.turnaround_days, 5)
        self.assertFalse(standard.priority)
        self.assertEqual(standard.priority_badge, "standard")

        urgent = self.create_request()
        urgent.requested_date = requests._date_after_working_days(urgent.request_date, 2)
        self.assertTrue(urgent.priority)
        self.assertEqual(urgent.priority_badge, "priority")

        # Manual writes cannot keep priority enabled when the requested date meets standard turnaround.
        urgent.write({"requested_date": expected_standard_date, "priority": True})
        self.assertFalse(urgent.priority)
        self.assertEqual(urgent.priority_badge, "standard")

        # Re-enabling urgency puts the priority request first in default search order.
        urgent.requested_date = requests._date_after_working_days(urgent.request_date, 1)
        ordered = requests.search([("id", "in", [standard.id, urgent.id])])
        self.assertEqual(list(ordered.ids), [urgent.id, standard.id])

    def test_collection_section_calendar_note_sync_and_stat_button_access(self):
        collector = self.env[MODEL_PERSON].create({"name": "Tran Van Thu", "login": "thu.collector"})
        self.customer.partner_id.phone = "+84901234567"
        task_type = self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        start = datetime(2026, 12, 1, 2, 0)
        note = "Contact: Tran Van Khach (+84901234567)\nSamples: Bottled water (1 L)"
        task = self.env[MODEL_TASK].create(
            {
                "type_id": task_type.id,
                "name": f"Collect {self.request.code}",
                "document_model": MODEL_TEST_REQUEST,
                "document_id": self.request.id,
                "assignee_id": collector.id,
                "status": "assigned",
                "planned_start": start,
                "planned_end": start + timedelta(minutes=60),
                "deadline": start + timedelta(hours=2),
                "place": "Gate 2, 12 Le Loi",
                "note": note,
            }
        )

        self.assertEqual(task.location_display, "Gate 2, 12 Le Loi")
        event = self.env["calendar.event"].search([("medilab_task_id", "=", task.id)])
        self.assertEqual(event.description, note)

        self.request.invalidate_recordset()
        self.assertEqual(self.request.collection_task_count, 1)
        self.assertEqual(self.request.collection_place, "Gate 2, 12 Le Loi")
        self.assertEqual(self.request.collection_assignee_id, collector)
        self.assertTrue(self.request.collection_appointment_display)
        self.assertIn("+84901234567", self.request.customer_contact_display or "")

        reader = new_test_user(
            self.env,
            login="lab.request.only",
            groups=f"base.group_user,{TEST_REQUEST_READER_GROUP}",
        )
        reader_perm = self.env[MODEL_PERMISSION].search([("code", "=", "test_request.read.all")], limit=1)
        reader_person = self.env[MODEL_PERSON].create(
            {
                "name": "Lab Reader",
                "login": "lab.request.only.person",
                "user_id": reader.id,
                "permission_ids": [Command.set([persisted_id(reader_perm)])],
            }
        )
        request_as_reader = self.request.with_user(reader)
        self.assertEqual(request_as_reader.collection_task_count, 1)
        self.assertFalse(request_as_reader.can_open_collection_tasks)

        task_perm = self.env[MODEL_PERMISSION].search([("code", "=", "task.read.all")], limit=1)
        reader_person.permission_ids = [Command.link(persisted_id(task_perm))]
        request_as_reader.invalidate_recordset(["can_open_collection_tasks"])
        self.assertTrue(request_as_reader.can_open_collection_tasks)
        action = request_as_reader.action_open_collection_tasks()
        self.assertEqual(action["res_model"], MODEL_TASK)
