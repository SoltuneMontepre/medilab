from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.binary import BinaryBytes

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TEST_OUTSOURCE,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

REASON = "The customer needs the lead result before an inspection."
REPORT = b"%PDF-1.4 Northern Testing Laboratory report"
REPORT_NAME = "northern-report.pdf"
ATTACHED = {"report_file": BinaryBytes(REPORT), "report_filename": REPORT_NAME}


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOutsourcingAgreement(DispatchCase):
    """A lead test keeps to the method the customer accepted on the quotation and goes to any subcontractor with that
    method; ICP-MS is another method, tested in-house and by Northern. The subcontractor's report stays with the
    dispatch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 10643:2014", "name": "Lead by ICP-MS", "field_id": cls.testing_field.id}
        )
        cls.icp_in_house, cls.icp_northern = cls.env[MODEL_PARAMETER_METHOD].create(
            [
                {"parameter_id": cls.parameter.id, "method_id": icp.id, "department_id": cls.department.id},
                {"parameter_id": cls.parameter.id, "method_id": icp.id, "subcontractor_id": cls.northern.id},
            ]
        )
        for way in (cls.icp_in_house, cls.icp_northern):
            cls.offer(cls.parameter, cls.sample_type, way)

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

    def wizard(self, test, way, reason: str | bool = False):
        return self.as_person(self.env[MODEL_SAMPLE_TEST_OUTSOURCE], self.head).create(
            {"sample_test_id": test.id, "parameter_method_id": way.id, "reason": reason}
        )

    def test_a_suggestion_goes_to_any_subcontractor_with_the_accepted_method(self):
        test = self.accepted_test(self.southern_way)

        self.assertEqual(test.outsourcing_method_ids, self.northern_way | self.southern_way)
        dispatch = self.wizard(test, self.northern_way).action_outsource()

        self.assertEqual(dispatch["res_model"], MODEL_SUBCONTRACT_DISPATCH)
        self.assertEqual(test.status, "outsourced")
        self.assertEqual(test.subcontractor_id, self.northern)
        self.assertEqual(test.accepted_method_id, self.southern_way)

    def test_a_test_accepted_in_house_is_outsourced_straight_away_with_the_same_method(self):
        test = self.accepted_test(self.pair, suggested=False)

        self.assertEqual(test.outsourcing_method_ids, self.northern_way | self.southern_way)
        dispatch = self.as_person(test, self.head)._outsource_now(self.southern_way, REASON)

        self.assertEqual(dispatch.subcontractor_id, self.southern)
        self.assertEqual(test.parameter_method_id, self.southern_way)
        self.assertEqual(test.emergency_outsource_reason, REASON)

    def test_outsourcing_with_another_method_is_refused(self):
        test = self.accepted_test(self.pair)

        self.assertIn(self.icp_northern, test.subcontracted_method_ids)
        self.assertNotIn(self.icp_northern, test.outsourcing_method_ids)
        with self.assertRaisesRegex(UserError, "revised quotation"):
            self.wizard(test, self.icp_northern, REASON).action_outsource()
        with self.assertRaisesRegex(UserError, "revised quotation"):
            self.as_person(test, self.head)._outsource_now(self.icp_northern, REASON)
        with self.assertRaisesRegex(ValidationError, "another method needs a revised quotation"):
            test.parameter_method_id = self.icp_in_house
        self.assertEqual(test.parameter_method_id, self.pair)
        self.assertFalse(test.emergency_outsource_reason)

    def test_a_test_is_never_outsourced_to_its_own_customer(self):
        own = self.env[MODEL_SUBCONTRACTOR].create({"partner_id": self.customer.partner_id.id})
        own_way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": self.method.id, "subcontractor_id": own.id}
        )
        self.offer(self.parameter, self.sample_type, own_way)
        test = self.accepted_test(self.pair)

        self.assertNotIn(own_way, test.subcontracted_method_ids)
        self.assertNotIn(own_way, test.outsourcing_method_ids)
        with self.assertRaisesRegex(UserError, "not a subcontracted way"):
            self.as_person(test, self.head)._outsource_now(own_way, REASON)
        with self.assertRaisesRegex(ValidationError, "own request"):
            test.parameter_method_id = own_way
        self.assertNotEqual(test.status, "outsourced")

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
