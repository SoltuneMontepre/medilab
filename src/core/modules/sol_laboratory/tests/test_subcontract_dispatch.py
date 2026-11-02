from ast import literal_eval

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACT_DISPATCH, MODEL_TEST_RESULT
from odoo.addons.sol_laboratory.services.record_id import persisted_id
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestSubcontractDispatch(DispatchCase):
    def test_accepting_a_suggestion_outsources_the_test_into_the_subcontractor_draft_dispatch(self):
        other = self.add_test()
        other.outsourcing_suggested = True

        dispatch = self.outsource()

        self.assertEqual(self.test.status, "outsourced")
        self.assertEqual(self.test.parameter_method_id, self.northern_way)
        self.assertFalse(self.test.outsourcing_suggested)
        self.assertEqual(self.sample.status, "testing")
        self.assertEqual(dispatch.status, "draft")
        self.assertEqual(dispatch.subcontractor_id, self.northern)
        self.assertEqual(dispatch.sample_test_ids, self.test)
        other_way = self.northern_way.copy({"parameter_id": other.parameter_id.id})
        self.offer(other.parameter_id, self.sample_type, other_way)
        self.assertEqual(self.outsource(other, other_way), dispatch)
        self.assertEqual(dispatch.sample_test_ids, self.test | other)

    def test_a_subcontractor_with_an_expired_accreditation_cannot_be_chosen(self):
        self.assertNotIn(self.coastal_way, self.test.subcontracted_method_ids)
        with self.assertRaises(UserError):
            self.outsource(way=self.coastal_way)
        with self.assertRaises(ValidationError):
            self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.head).create(
                {"subcontractor_id": self.coastal.id}
            )

    def test_a_dispatch_records_either_sample_delivery_staff_or_a_delivery_service(self):
        dispatch = self.as_person(self.outsource(), self.head)
        dispatch.expected_date = "2026-10-16"

        with self.assertRaises(UserError):
            dispatch.action_send()
        with self.assertRaises(ValidationError):
            dispatch.write({"courier_id": self.courier.id, "delivery_service": "Viettel Post, VTP 8402 1157 2210"})
        dispatch.delivery_service = "Viettel Post, VTP 8402 1157 2210"
        dispatch.action_send()

        self.assertEqual(dispatch.status, "sent")
        self.assertEqual(str(dispatch.sent_date), "2026-10-12")

    def test_a_dispatch_moves_only_by_its_buttons_and_is_not_cancelled_once_results_exist(self):
        dispatch = self.send_dispatch(self.outsource())

        with self.assertRaises(UserError):
            dispatch.write({"status": "draft"})
        self.enter()
        with self.assertRaises(UserError):
            dispatch.action_cancel()
        self.assertEqual(dispatch.status, "sent")

    def test_a_sent_dispatch_appears_on_the_outsourcing_schedule_with_its_expected_date(self):
        dispatch = self.outsource()
        schedule = literal_eval(
            assert_instance(self.env.ref("sol_laboratory.action_medilab_subcontract_dispatch_schedule").domain, str)
        )
        dispatches = self.env[MODEL_SUBCONTRACT_DISPATCH]
        self.assertNotIn(dispatch, dispatches.search(schedule))

        self.send_dispatch(dispatch)

        self.assertIn(dispatch, dispatches.search(schedule))
        self.assertEqual(str(dispatch.expected_date), "2026-10-16")

    def test_sample_delivery_staff_see_the_dispatches_they_carry_with_the_subcontractor_and_date_sent(self):
        dispatch = self.send_dispatch(self.outsource())

        to_carry = literal_eval(
            assert_instance(self.env.ref("sol_laboratory.action_medilab_subcontract_dispatch_carry").domain, str)
        )
        carried = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.courier).search(to_carry)

        self.assertEqual(carried, dispatch)
        self.assertEqual(carried.subcontractor_id, self.northern)
        self.assertEqual(str(carried.sent_date), "2026-10-12")
        self.assertFalse(self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.chemist).search([]))

    def test_a_subcontractor_user_sees_the_sent_dispatches_of_their_own_subcontractor_only(self):
        dispatches = self.env[MODEL_SUBCONTRACT_DISPATCH]
        northern = self.outsource()
        self.assertFalse(dispatches._portal_dispatches(self.northern_user))
        self.send_dispatch(northern)
        other = self.add_test()
        other.outsourcing_suggested = True
        southern_way = self.southern_way.copy({"parameter_id": other.parameter_id.id})
        self.offer(other.parameter_id, self.sample_type, southern_way)

        southern = self.send_dispatch(self.outsource(other, southern_way))

        self.assertEqual(dispatches._portal_dispatches(self.northern_user), northern)
        self.assertEqual(dispatches._portal_dispatches(self.southern_user), southern)

    def test_a_subcontractor_result_records_its_user_and_waits_for_approval_like_any_other(self):
        dispatch = self.send_dispatch(self.outsource())
        portal = self.env[MODEL_SUBCONTRACT_DISPATCH].with_user(self.northern_user)

        result = portal._portal_dispatches(self.northern_user)._portal_enter_result(self.test.id, "0,008", "")

        self.assertEqual(result.entered_by_id, self.northern_user)
        self.assertEqual(result.value, 0.008)
        self.assertEqual(result.status, "none")
        self.assertFalse(result.machine_id)
        self.assertEqual(self.test.status, "outsourced")
        with self.assertRaises(UserError):
            dispatch._portal_enter_result(self.test.id, "0.009", "")
        self.as_person(result, self.tester).conclusion = "pass"
        self.send(result)
        self.assertEqual(self.test.status, "result_entered")
        self.approve(result)
        self.assertEqual(result.status, "approved")
        self.assertEqual(self.test.status, "approved")

    def test_a_tester_enters_an_outsourced_result_only_once_the_dispatch_is_sent(self):
        dispatch = self.outsource()
        with self.assertRaises(UserError):
            self.enter()

        self.send_dispatch(dispatch)
        result = self.enter()

        self.assertEqual(result.entered_by_id, self.tester.user_id)
        with self.assertRaises(ValidationError):
            result.machine_id = self.fast

    def test_a_rejected_outsourced_result_sends_the_test_back_to_its_subcontractor(self):
        self.send_dispatch(self.outsource())
        result = self.enter()
        self.send(result)

        self.as_person(result, self.head).action_reject("The subcontractor's report shows another sample.")

        self.assertEqual(self.test.status, "outsourced")
        retest = (
            self.env[MODEL_TEST_RESULT]
            .with_user(self.northern_user)
            .sudo()
            .create({"sample_test_id": self.test.id, "value": 0.006})
        )
        self.assertEqual(retest.attempt, 2)

    def test_a_test_joins_a_dispatch_only_through_the_dispatch(self):
        dispatch = self.outsource()
        in_house = self.add_test()

        with self.assertRaises(UserError):
            self.as_person(in_house, self.head).write({"dispatch_ids": [Command.link(persisted_id(dispatch))]})
        with self.assertRaises(ValidationError):
            self.as_person(self.test, self.head).write({"parameter_method_id": self.southern_way.id})
        self.assertEqual(dispatch.sample_test_ids, self.test)
        self.assertEqual(self.test.subcontractor_id, self.northern)
