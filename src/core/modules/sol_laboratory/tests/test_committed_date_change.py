from datetime import date, datetime

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_COMMITTED_DATE_CHANGE


@tagged("post_install", "-at_install")
class TestCommittedDateChange(RequestCase):
    """The request promises results on 20 October; its sample test's due date follows."""

    def change(self, new_date, confirmation="The customer agreed by email on 12 October."):
        return self.env[MODEL_COMMITTED_DATE_CHANGE].create(
            {"request_id": self.request.id, "new_date": new_date, "confirmation": confirmation}
        )

    def test_a_change_records_the_old_and_new_date_and_moves_the_due_date(self):
        due = self.sample.test_ids.due_date
        assert isinstance(due, datetime)

        change = self.change("2026-10-27")

        self.assertEqual(change.old_date, date(2026, 10, 20))
        self.assertEqual(self.request.committed_date, date(2026, 10, 27))
        new_due = self.sample.test_ids.due_date
        assert isinstance(new_due, datetime)
        self.assertGreater(new_due, due)
        self.assertEqual(self.request.committed_date_change_ids, change)

    def test_a_change_needs_the_customer_s_confirmation(self):
        with self.assertRaisesRegex(UserError, "how the customer agreed"):
            self.change("2026-10-27", confirmation="  ")

    def test_the_committed_date_changes_only_through_a_recorded_change(self):
        head = self.head_of(self.department).user_id

        with self.assertRaisesRegex(UserError, "Change Committed Date"):
            self.request.with_user(head).write({"committed_date": "2026-10-27"})

    def test_a_recorded_change_is_neither_edited_nor_deleted(self):
        change = self.change("2026-10-27")

        with self.assertRaisesRegex(UserError, "cannot be edited"):
            change.confirmation = "Another call"
        with self.assertRaisesRegex(UserError, "cannot be deleted"):
            change.unlink()

    def test_receipt_fixes_the_date_of_a_request_without_one(self):
        request = self.create_request()
        request.with_context(medilab_changing_committed_date=True).write(
            {"committed_date": False, "turnaround_days": 5}
        )
        request.action_confirm()

        head = self.head_of(self.department).user_id

        request.sample_ids.with_user(head).action_receive("1 bottle of 1 L", "good")

        committed = request.committed_date
        assert isinstance(committed, date)
        self.assertGreaterEqual((committed - fields.Date.today()).days, 5)

    def test_the_change_form_records_the_change_of_its_request(self):
        form = Form(self.env[MODEL_COMMITTED_DATE_CHANGE].with_context(default_request_id=self.request.id))
        self.assertEqual(form.current_date, date(2026, 10, 20))
        form.new_date = date(2026, 10, 27)
        form.confirmation = "The customer agreed by phone."

        change = form.save()

        self.assertEqual(change.request_id, self.request)
        self.assertEqual(self.request.committed_date, date(2026, 10, 27))
