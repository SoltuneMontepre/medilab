from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .change_request_case import ChangeRequestCase


@tagged("post_install", "-at_install")
class TestChangeRequestRaising(ChangeRequestCase):
    def test_a_change_request_without_what_to_change_or_why_is_refused(self):
        result = self.complete()

        for change, reason in (("", "The dilution was 4."), ("Change the lead value to 0.006.", "  ")):
            with self.assertRaises(UserError):
                self.raise_on(result, change=change, reason=reason)

    def test_a_person_who_cannot_edit_the_document_type_cannot_raise_one(self):
        result = self.complete()

        for person in (self.lab_head, self.courier):
            with self.assertRaises(AccessError):
                self.raise_on(result, person=person)

    def test_only_a_document_whose_process_is_completed_takes_a_change_request(self):
        result = self.enter()
        self.send(result)
        with self.assertRaises(UserError):
            self.raise_on(result)

        # A rejected result is corrected by a retest.
        self.as_person(result, self.head).action_reject("The blank read above the limit of detection.")

        with self.assertRaises(UserError):
            self.raise_on(result)

    def test_a_document_has_one_open_change_request_at_a_time(self):
        result = self.complete()
        self.raise_on(result)

        with self.assertRaises(UserError):
            self.raise_on(result, person=self.other_tester)

    def test_the_requester_follows_the_status_at_every_step(self):
        result = self.complete()
        request = self.raise_on(result)
        self.assertEqual(request.status, "requested")

        self.sign(request)

        self.assertEqual(request.status, "applied")
        with self.assertRaises(AccessError):
            self.as_person(request, self.other_tester).read(["status"])
