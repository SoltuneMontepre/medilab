from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_CALENDAR_EVENT,
    MODEL_CHEMICAL,
    MODEL_DEPARTMENT,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
    MODEL_SUBCONTRACTOR,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TASK_REMINDER


@tagged("post_install", "-at_install")
class TestAuditRecording(AuditCase):
    def test_changing_a_limit_shows_who_when_and_from_what_to_what(self):
        self.limit.with_user(self.editor).max_value = 0.02

        entry = self.entries(self.limit, "edit")
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry.user_id, self.editor)
        self.assertTrue(entry.create_date)
        self.assertEqual(entry.source, "screen")
        self.assertEqual(self.changes(entry), {"max_value": ("0.01", "0.02")})

    def test_creating_records_the_fields_given_a_value(self):
        entry = self.entries(self.limit, "create")

        self.assertEqual(
            self.changes(entry),
            {
                "regulation_id": (False, f"{self.regulation.display_name} (#{self.regulation.id})"),
                "parameter_id": (False, f"{self.parameter.display_name} (#{self.parameter.id})"),
                "unit_id": (False, f"{self.unit.display_name} (#{self.unit.id})"),
                "max_set": (False, "True"),
                "max_value": (False, "0.01"),
                "decimals": (False, "3"),
            },
        )

    def test_archiving_is_its_own_action(self):
        parameter = self.create_parameter("Arsenic (As)", self.group)

        parameter.action_archive()

        self.assertEqual(self.changes(self.entries(parameter, "archive")), {"active": ("True", "False")})
        self.assertFalse(self.entries(parameter, "edit"))

    def test_deleting_keeps_the_name_of_the_document(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-099", "name": "Nitric acid 65%"})
        name = chemical.display_name

        chemical.unlink()

        entry = self.entries(chemical, "delete")
        self.assertEqual(entry.note, name)
        self.assertFalse(entry.change_ids)

    def test_the_entries_of_a_deleted_document_keep_its_name(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-104", "name": "Perchloric acid 70%"})
        name = chemical.display_name
        chemical.unlink()

        created = self.entries(chemical, "create")
        self.assertEqual(created.document_name, name)
        self.assertEqual(
            self.env[MODEL_AUDIT_ENTRY].sudo().search([("document_name", "ilike", "Perchloric")]),
            self.entries(chemical),
        )

    def test_writing_the_same_value_records_nothing(self):
        self.limit.max_value = 0.01

        self.assertFalse(self.entries(self.limit, "edit"))

    def test_bookkeeping_and_excluded_fields_are_left_out(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-100", "name": "Sulfuric acid", "formula": "H2SO4"})
        self.patch(type(chemical), "_audit_exclude", ("formula",))

        chemical.write({"name": "Sulfuric acid 98%", "formula": "H₂SO₄"})

        self.assertEqual(set(self.changes(self.entries(chemical, "edit"))), {"name"})

    def test_details_of_a_delegated_contact_are_recorded_on_the_contact_and_in_the_history(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"})

        subcontractor.email = "lab@northern.example"

        edit = self.entries(subcontractor.partner_id, "edit")
        self.assertEqual(self.changes(edit)["email"], (False, "lab@northern.example"))
        self.assertFalse(self.entries(subcontractor, "edit"))
        self.assertIn(edit, self.history(subcontractor, self.auditor))

    def test_turning_a_notification_event_off_is_recorded_with_its_recipients_in_its_history(self):
        event = self.env[MODEL_MAIL_MESSAGE_SUBTYPE].search([("code", "=", EVENT_TASK_REMINDER)])
        recipient = self.env[MODEL_NOTIFICATION_EVENT_RECIPIENT].create(
            {"event_id": event.id, "department_id": self.env[MODEL_DEPARTMENT].create({"name": "Microbiology"}).id}
        )

        event.enabled = False

        self.assertEqual(self.changes(self.entries(event, "edit")), {"enabled": ("True", "False")})
        self.assertIn(self.entries(recipient, "create"), self.history(event, self.auditor))

    def test_a_calendar_event_is_recorded(self):
        meeting = self.env[MODEL_CALENDAR_EVENT].create(
            {"name": "Method validation review", "start": "2026-10-20 08:00:00", "stop": "2026-10-20 09:00:00"}
        )

        meeting.name = "Method validation review, ICP-MS"

        self.assertEqual(
            self.changes(self.entries(meeting, "edit"))["name"],
            ("Method validation review", "Method validation review, ICP-MS"),
        )

    def test_an_action_rolled_back_leaves_no_entry(self):
        with self.assertRaises(RuntimeError), self.env.cr.savepoint():
            self.limit.max_value = 0.05
            raise RuntimeError("The change is cancelled.")

        self.assertFalse(self.entries(self.limit, "edit"))

    def test_a_scheduled_job_acts_as_the_system(self):
        self.limit.with_context(cron_id=1).max_value = 0.03

        entry = self.entries(self.limit, "edit")
        self.assertEqual(entry.source, "job")
        self.assertFalse(entry.user_id)

    def test_a_feature_records_its_own_actions(self):
        self.regulation.with_user(self.editor)._audit("approve", note="Approved for bottled water testing")

        entry = self.entries(self.regulation, "approve")
        self.assertEqual(entry.user_id, self.editor)
        self.assertEqual(entry.note, "Approved for bottled water testing")
