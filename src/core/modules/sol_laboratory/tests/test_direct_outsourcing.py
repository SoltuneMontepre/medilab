from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .audit_case import AuditLookup
from .dispatch_case import DISPATCH_PERMISSIONS, DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_SAMPLE_TEST_OUTSOURCE

REASON = "The AAS is under repair and the customer needs the lead result before an inspection."


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestDirectOutsourcing(AuditLookup, DispatchCase):
    """The lead test has no outsourcing suggestion: its head of department outsources it straight away."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test.outsourcing_suggested = False

    def outsource_now(self, test=None, person=None, reason=REASON, way=None):
        return self.as_person(test or self.test, person or self.head)._outsource_now(way or self.northern_way, reason)

    def wizard(self, test):
        return self.as_person(self.env[MODEL_SAMPLE_TEST_OUTSOURCE], self.head).create(
            {"sample_test_id": test.id, "parameter_method_id": self.northern_way.id}
        )

    def lead_test(self, assignee=None):
        """Another lead test on the sample, assigned to the person or waiting in the department queue."""
        test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": self.parameter.id})
        self.testing_task(test, assignee)
        return test

    def test_outsourcing_straight_away_sends_the_test_with_its_reason_into_the_draft_dispatch(self):
        booking = self.schedule(self.test, self.tester)

        dispatch = self.outsource_now()

        self.assertEqual(self.test.status, "outsourced")
        self.assertEqual(self.test.parameter_method_id, self.northern_way)
        self.assertEqual(self.test.emergency_outsource_reason, REASON)
        self.assertEqual(booking.status, "cancelled")
        self.assertEqual(self.sample.status, "testing")
        self.assertEqual(dispatch.status, "draft")
        self.assertEqual(dispatch.subcontractor_id, self.northern)
        self.assertEqual(dispatch.sample_test_ids, self.test)
        recorded = [self.changes(entry).get("emergency_outsource_reason") for entry in self.entries(self.test, "edit")]
        self.assertIn((False, REASON), recorded)

    def test_a_waiting_test_is_outsourced_straight_away(self):
        test = self.lead_test()
        self.assertEqual(test.status, "waiting")

        self.outsource_now(test)

        self.assertEqual(test.status, "outsourced")

    def test_outsourcing_straight_away_without_a_reason_is_refused(self):
        with self.assertRaises(UserError):
            self.outsource_now(reason=" ")

        self.assertEqual(self.test.status, "assigned")

    def test_a_test_in_testing_cannot_be_outsourced_straight_away(self):
        booking = self.schedule(self.test, self.tester)
        self.as_person(booking, self.tester).action_start()

        with self.assertRaises(UserError):
            self.outsource_now()

        self.assertEqual(self.test.status, "testing")

    def test_only_the_department_testing_it_outsources_a_test_straight_away(self):
        outsider = self.create_person(
            "Vo Thi Hoa",
            self.microbiology,
            "hoa.vo",
            permissions=("sample_test.read.all", "sample_test.edit.all", *DISPATCH_PERMISSIONS),
        )

        with self.assertRaises(UserError):
            self.outsource_now(person=outsider)
        with self.assertRaises(AccessError):
            self.outsource_now(person=self.tester)
        self.assertEqual(self.test.status, "assigned")

    def test_a_subcontractor_with_an_expired_accreditation_cannot_be_chosen_straight_away(self):
        with self.assertRaises(UserError):
            self.outsource_now(way=self.coastal_way)

    def test_the_wizard_asks_for_a_reason_only_when_the_test_has_no_suggestion(self):
        suggested = self.lead_test(self.tester)
        suggested.outsourcing_suggested = True

        self.wizard(suggested).action_outsource()
        wizard = self.wizard(self.test)
        with self.assertRaises(UserError):
            wizard.action_outsource()
        wizard.reason = REASON
        wizard.action_outsource()

        self.assertEqual(suggested.status, "outsourced")
        self.assertFalse(suggested.emergency_outsource_reason)
        self.assertEqual(self.test.status, "outsourced")
        self.assertEqual(self.test.emergency_outsource_reason, REASON)
