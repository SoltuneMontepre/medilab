from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.binary import BinaryBytes

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TEST_OUTSOURCE,
    MODEL_SUBCONTRACT_DISPATCH,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

REASON = "The customer needs the lead result before an inspection."
REPORT = b"%PDF-1.4 Northern Testing Laboratory report"
REPORT_NAME = "northern-report.pdf"
ATTACHED = {"report_file": BinaryBytes(REPORT), "report_filename": REPORT_NAME}


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOutsourcingAgreement(DispatchCase):
    """A lead test keeps to the way of testing the customer accepted on the quotation; the subcontractor's report stays
    with the dispatch."""

    def accepted_test(self, way, suggested=True):
        test = self.env[MODEL_SAMPLE_TEST].create(
            {
                "sample_id": self.sample.id,
                "parameter_id": self.parameter.id,
                "parameter_method_id": way.id,
                "accepted_method_id": way.id,
                "outsourcing_suggested": suggested,
            }
        )
        self.testing_task(test, self.tester)
        return test

    def wizard(self, test, way):
        return self.as_person(self.env[MODEL_SAMPLE_TEST_OUTSOURCE], self.head).create(
            {"sample_test_id": test.id, "parameter_method_id": way.id}
        )

    def test_accepting_a_suggestion_refuses_a_way_other_than_the_accepted_one(self):
        test = self.accepted_test(self.southern_way)

        self.assertIn(self.northern_way, test.subcontracted_method_ids)
        self.assertEqual(test.outsourcing_method_ids, self.southern_way)
        with self.assertRaises(UserError):
            self.outsource(test, self.northern_way)
        with self.assertRaises(UserError):
            self.wizard(test, self.northern_way).action_outsource()
        self.assertEqual(test.parameter_method_id, self.southern_way)
        self.assertNotEqual(test.status, "outsourced")

        dispatch = self.outsource(test, self.southern_way)

        self.assertEqual(dispatch.subcontractor_id, self.southern)
        self.assertEqual(test.status, "outsourced")

    def test_outsourcing_straight_away_refuses_a_way_other_than_the_accepted_one(self):
        test = self.accepted_test(self.southern_way, suggested=False)

        with self.assertRaises(UserError):
            self.as_person(test, self.head)._outsource_now(self.northern_way, REASON)
        self.assertFalse(test.emergency_outsource_reason)

        dispatch = self.as_person(test, self.head)._outsource_now(self.southern_way, REASON)

        self.assertEqual(dispatch.subcontractor_id, self.southern)
        self.assertEqual(test.emergency_outsource_reason, REASON)

    def test_a_test_accepted_in_house_is_not_outsourced_before_a_revised_quotation(self):
        in_house = self.parameter.method_ids.filtered("department_id")[:1]
        test = self.accepted_test(in_house)

        self.assertTrue(test.subcontracted_method_ids)
        self.assertFalse(test.outsourcing_method_ids)
        self.assertFalse(self.wizard(test, self.northern_way).outsourcing_method_ids)
        with self.assertRaises(UserError):
            self.wizard(test, self.northern_way).action_outsource()
        with self.assertRaises(UserError):
            self.as_person(test, self.head)._outsource_now(self.northern_way, REASON)
        self.assertEqual(test.parameter_method_id, in_house)

    def test_the_department_of_the_default_way_outsources_a_test_accepted_on_a_subcontracted_way(self):
        test = self.accepted_test(self.northern_way)

        self.assertEqual(self.sample._department_by_test()[test], self.department)

    def test_a_sample_test_is_placed_in_one_dispatch_only(self):
        dispatch = self.outsource()
        dispatches = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.head)

        with self.assertRaises(ValidationError):
            dispatches.create(
                {"subcontractor_id": self.northern.id, "sample_test_ids": [Command.link(persisted_id(self.test))]}
            )
        self.as_person(dispatch, self.head).action_cancel()
        other = dispatches.create(
            {"subcontractor_id": self.northern.id, "sample_test_ids": [Command.link(persisted_id(self.test))]}
        )

        self.assertEqual(other.sample_test_ids, self.test)

    def test_the_subcontractor_report_is_attached_to_a_sent_dispatch(self):
        dispatch = self.as_person(self.outsource(), self.head)

        with self.assertRaises(UserError):
            dispatch.write(ATTACHED)
        self.send_dispatch(dispatch)
        dispatch.write(ATTACHED)
        dispatch.action_receive()
        with self.assertRaises(UserError):
            dispatch.write({"report_file": False, "report_filename": False})

        self.assertEqual(dispatch.report_file.content, REPORT)
        self.assertEqual(dispatch.report_filename, REPORT_NAME)

    def test_only_people_who_read_dispatches_read_the_subcontractor_report(self):
        dispatch = self.send_dispatch(self.outsource())
        dispatch.write(ATTACHED)
        report = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [("res_model", "=", dispatch._name), ("res_id", "=", dispatch.id), ("res_field", "=", "report_file")]
            )
        )
        self.assertTrue(report)

        carried = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.courier).browse(dispatch.id)
        self.assertEqual(carried.subcontractor_id, self.northern)
        with self.assertRaises(AccessError):
            carried.read(["report_file"])
        for user in (self.courier.user_id, self.southern_user, self.northern_user):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                report.with_user(user).read(["raw"])
        self.assertFalse(
            self.env[MODEL_SUBCONTRACT_DISPATCH]._portal_dispatches(self.southern_user, dispatch.id),
        )
