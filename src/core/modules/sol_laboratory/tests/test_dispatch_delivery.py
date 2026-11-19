from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.jobs import DISPATCH_ACCREDITATION_LAPSED_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_SCHEDULED_JOB,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACT_DISPATCH_FAILURE,
    MODEL_SUBCONTRACT_DISPATCH_HANDOVER,
    MODEL_SUBCONTRACTOR_CONTACT,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

REASON = "The cold box lost its cooling on the way; the samples came back to the laboratory."
SUBCONTRACTOR_PERMISSIONS = ("subcontractor.edit.all",)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestDispatchDelivery(DispatchCase):
    """The head heads the lead test's department, and Vo Thi Giang carries the dispatch to Northern, which takes six
    days to send results back."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department.manager_id = cls.head.employee_id
        cls.northern_way.turnaround_days = 6

    def draft(self):
        dispatch = self.as_person(self.outsource(), self.head)
        dispatch.courier_id = self.courier
        return dispatch

    def notifications(self, dispatch, kind):
        return self.env[MODEL_MAIL_MESSAGE].search(
            [("notification_key", "like", f"subcontract_dispatch:{dispatch.id}:{kind}%")]
        )

    def portal(self, dispatch, user=None):
        user = user or self.northern_user
        return self.env[MODEL_SUBCONTRACT_DISPATCH].with_user(user)._portal_dispatches(user, dispatch.id)

    def test_the_expected_date_is_the_date_sent_plus_the_longest_turnaround(self):
        dispatch = self.draft()

        dispatch.action_send()

        self.assertEqual(str(dispatch.sent_date), "2026-10-12")
        self.assertEqual(str(dispatch.expected_date), "2026-10-18")

    def test_an_entered_expected_date_is_kept(self):
        dispatch = self.draft()
        dispatch.expected_date = "2026-10-20"

        dispatch.action_send()

        self.assertEqual(str(dispatch.expected_date), "2026-10-20")

    def test_the_sample_delivery_staff_hand_the_dispatch_to_a_delivery_service_with_its_tracking_number(self):
        dispatch = self.draft()
        carried = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.courier).browse(dispatch.id)
        self.assertTrue(carried.can_hand_over)
        self.assertFalse(self.as_person(dispatch, self.head).can_hand_over)
        wizards = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH_HANDOVER], self.courier)

        with self.assertRaisesRegex(UserError, "tracking number"):
            wizards.create({"dispatch_id": dispatch.id, "delivery_service": "Viettel Post"}).action_hand_over()
        wizards.create(
            {"dispatch_id": dispatch.id, "delivery_service": "Viettel Post", "tracking_number": "VTP 8402 1157 2210"}
        ).action_hand_over()

        self.assertEqual(dispatch.status, "sent")
        self.assertEqual(dispatch.courier_id, self.courier)
        self.assertEqual(dispatch.tracking_number, "VTP 8402 1157 2210")
        self.assertEqual(str(dispatch.expected_date), "2026-10-18")
        with self.assertRaises(UserError):
            self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH_HANDOVER], self.head).create(
                {"dispatch_id": dispatch.id}
            ).action_hand_over()

    def test_the_subcontractor_confirms_receipt_on_the_portal_and_the_head_is_told(self):
        dispatch = self.draft()
        self.assertFalse(self.portal(dispatch))
        dispatch.action_send()

        with self.assertRaisesRegex(UserError, "Confirm receipt"):
            self.portal(dispatch)._portal_enter_result(self.test.id, "0.008", "")
        self.portal(dispatch)._portal_confirm_receipt()

        self.assertEqual(dispatch.status, "received")
        self.assertEqual(str(dispatch.received_date), "2026-10-12")
        self.assertIn(self.head.user_id.partner_id, self.portal(dispatch)._heads())
        self.assertTrue(self.notifications(dispatch, "received"))
        self.assertTrue(self.portal(dispatch)._portal_enter_result(self.test.id, "0.008", ""))

    def test_the_head_marks_receipt_for_a_subcontractor_without_the_portal(self):
        dispatch = self.draft()
        dispatch.action_send()

        dispatch.action_receive()

        self.assertEqual(dispatch.status, "received")
        self.assertTrue(self.as_person(self.test, self.tester).can_enter_result)

    def test_a_failed_delivery_cancels_the_sent_dispatch_and_keeps_its_tests_outsourced(self):
        dispatch = self.draft()
        dispatch.action_send()
        carried = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.courier).browse(dispatch.id)
        self.assertTrue(carried.can_report_failure)
        failures = self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH_FAILURE], self.courier)

        with self.assertRaisesRegex(UserError, "reason"):
            carried._report_failed_delivery(" ")
        failures.create({"dispatch_id": dispatch.id, "reason": REASON}).action_confirm()

        self.assertEqual(dispatch.status, "cancelled")
        self.assertEqual(dispatch.failure_reason, REASON)
        self.assertEqual(self.test.status, "outsourced")
        self.assertTrue(self.notifications(dispatch, "delivery_failed"))
        again = self.outsource_into_new_dispatch()
        self.assertNotEqual(again, dispatch)

    def outsource_into_new_dispatch(self):
        return self.as_person(self.env[MODEL_SUBCONTRACT_DISPATCH], self.head).create(
            {"subcontractor_id": self.northern.id, "sample_test_ids": [Command.link(persisted_id(self.test))]}
        )

    def test_a_lapsed_accreditation_tells_the_head_and_the_tests_move_to_another_subcontractor(self):
        dispatch = self.draft()
        self.northern.accreditation_expiry = "2026-10-01"

        self.env[MODEL_SCHEDULED_JOB]._run_key(DISPATCH_ACCREDITATION_LAPSED_JOB)

        self.assertTrue(self.notifications(dispatch, "accreditation_lapsed"))
        with self.assertRaises(UserError):
            dispatch.action_send()
        self.assertFalse(self.test.can_move_subcontractor)
        dispatch.action_cancel()
        self.assertTrue(self.test.can_move_subcontractor)
        self.assertEqual(self.test.outsourcing_method_ids, self.southern_way)

        moved = self.as_person(self.test, self.head)._move_to_subcontractor(self.southern_way)

        self.assertEqual(moved.subcontractor_id, self.southern)
        self.assertEqual(moved.status, "draft")
        self.assertEqual(self.test.status, "outsourced")
        self.assertEqual(self.test.subcontractor_id, self.southern)

    def test_a_sent_dispatch_is_still_received_after_the_accreditation_lapses(self):
        dispatch = self.draft()
        dispatch.action_send()
        self.northern.accreditation_expiry = "2026-10-01"

        self.env[MODEL_SCHEDULED_JOB]._run_key(DISPATCH_ACCREDITATION_LAPSED_JOB)
        dispatch.action_receive()

        self.assertFalse(self.notifications(dispatch, "accreditation_lapsed"))
        self.assertEqual(dispatch.status, "received")

    def test_cancelling_the_test_request_cancels_its_outsourced_tests(self):
        dispatch = self.draft()

        self.request.sudo().action_cancel()

        self.assertEqual(self.test.status, "cancelled")
        self.assertFalse(dispatch.sample_test_ids)

    def test_a_received_dispatch_shows_a_cancelled_test_and_takes_no_result_for_it(self):
        dispatch = self.receive_dispatch(self.draft())

        self.request.sudo().action_cancel()

        self.assertEqual(self.test.status, "cancelled")
        self.assertEqual(dispatch.sample_test_ids, self.test)
        with self.assertRaises(UserError):
            self.portal(dispatch)._portal_enter_result(self.test.id, "0.008", "")

    def test_the_printed_dispatch_shows_the_tests_and_never_the_customer(self):
        dispatch = self.draft()
        dispatch.action_send()

        html = str(
            self.env["ir.actions.report"]._render_qweb_html(
                "sol_laboratory.action_report_subcontract_dispatch", dispatch.ids
            )[0]
        )

        self.assertIn(dispatch.code, html)
        self.assertIn(self.sample.code, html)
        self.assertIn(self.method.code, html)
        self.assertNotIn(self.customer.name, html)
        self.assertNotIn(self.request.code, html)

    def test_people_with_the_subcontractor_permission_add_its_contact_people(self):
        self.grant(self.head, *SUBCONTRACTOR_PERMISSIONS)
        person = (
            self.as_person(self.env[MODEL_SUBCONTRACTOR_CONTACT], self.head)
            .create({"subcontractor_id": self.northern.id, "name": "Pham Van Duc", "make_default": True})
            .action_add()
        )

        self.assertEqual(person.parent_id, self.northern.partner_id)
        self.assertEqual(self.northern.contact_person_id, person)
        self.assertIn(person, self.northern.contact_ids)
        with self.assertRaises(UserError):
            self.as_person(self.env[MODEL_SUBCONTRACTOR_CONTACT], self.courier).create(
                {"subcontractor_id": self.northern.id, "name": "Le Van Tam"}
            ).action_add()

    def test_an_archived_default_contact_stops_the_dispatch_being_sent(self):
        contact = self.env["res.partner"].create({"name": "Pham Van Duc", "parent_id": self.northern.partner_id.id})
        self.northern.contact_person_id = contact
        dispatch = self.draft()
        contact.active = False

        self.assertTrue(self.northern.contact_person_archived)
        self.assertTrue(dispatch.contact_person_archived)
        with self.assertRaisesRegex(UserError, "contact person"):
            dispatch.action_send()
