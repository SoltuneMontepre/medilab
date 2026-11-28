from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .assertions import assert_instance
from .plan_revision_case import AFTERNOON, THURSDAY, TUESDAY, WEDNESDAY, PlanRevisionCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PLAN_REVISION


@freeze_time(TUESDAY)
@tagged("post_install", "-at_install")
class TestPlanRevisionApproval(PlanRevisionCase):
    """Heads approve the moves of their own department; the revision applies when every move is approved."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant(cls.microbiology_head, "plan_revision.read.all", "plan_revision_move.read.all")
        cls.microbiologist.tz = "UTC"
        cls.m_test = cls.committed(cls.microbiology_way)
        cls.m = cls.booked(cls.m_test, cls.microbiologist)
        # A booking that has started cannot move, so M waits for Wednesday afternoon.
        cls.m._set({"starts_at": AFTERNOON, "ends_at": AFTERNOON + timedelta(minutes=45)})

    def two_department_revision(self):
        """A revision that moves Z of chemistry to Thursday and M of microbiology to the next free hour; the scheduler
        proposes revisions of one department, so this one is made by hand."""
        return self.env[MODEL_PLAN_REVISION].create(
            {
                "department_id": self.department.id,
                "reason": "Makes room for urgent work",
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "booking_id": booking.id,
                            "department_id": booking.department_id.id,
                            "machine_id": booking.machine_id.id,
                            "previous_starts_at": booking.starts_at,
                            "previous_ends_at": booking.ends_at,
                            "starts_at": start,
                            "ends_at": start
                            + (
                                assert_instance(booking.ends_at, datetime)
                                - assert_instance(booking.starts_at, datetime)
                            ),
                            "status": "proposed",
                        },
                    )
                    for booking, start in ((self.z, THURSDAY), (self.m, WEDNESDAY))
                ],
            }
        )

    def test_a_head_approves_only_the_moves_of_their_own_department(self):
        revision = self.two_department_revision()
        chemistry_move, microbiology_move = revision.move_ids.sorted("id")

        revision.with_user(self.head.user_id).action_approve()

        self.assertEqual((chemistry_move.status, chemistry_move.approved_by_id), ("approved", self.head))
        self.assertEqual((microbiology_move.status, microbiology_move.approved_by_id.id), ("proposed", False))
        self.assertEqual((revision.status, self.z.starts_at), ("proposed", WEDNESDAY))

        revision.with_user(self.microbiology_head.user_id).action_approve()

        self.assertEqual(microbiology_move.approved_by_id, self.microbiology_head)
        self.assertEqual((revision.status, {move.status for move in revision.move_ids}), ("applied", {"applied"}))
        self.assertEqual((self.z.starts_at, self.m.starts_at), (THURSDAY, WEDNESDAY))

    def test_a_person_who_edits_the_bookings_of_every_department_approves_every_move(self):
        revision = self.two_department_revision()
        self.grant(
            self.chemist,
            "plan_revision.read.all",
            "plan_revision_move.read.all",
            "machine_booking.read.all",
            "machine_booking.edit.all",
        )

        revision.with_user(self.chemist.user_id).action_approve()

        self.assertEqual(revision.move_ids.approved_by_id, self.chemist)
        self.assertEqual((revision.status, self.z.starts_at, self.m.starts_at), ("applied", THURSDAY, WEDNESDAY))

    def test_a_person_who_may_not_edit_the_bookings_of_any_affected_department_decides_nothing(self):
        revision = self.two_department_revision()

        for person in (self.tester, self.chemist):
            with self.subTest(person=person.name):
                self.grant(person, "plan_revision.read.all", "plan_revision_move.read.all")
                with self.assertRaises(AccessError):
                    revision.with_user(person.user_id).action_approve()
                with self.assertRaises(AccessError):
                    revision.with_user(person.user_id).action_reject()

        self.assertEqual({move.status for move in revision.move_ids}, {"proposed"})

    def test_a_head_cannot_approve_again_a_move_already_approved(self):
        revision = self.two_department_revision()
        revision.with_user(self.head.user_id).action_approve()

        with self.assertRaisesRegex(UserError, "No move waits for your approval"):
            revision.with_user(self.head.user_id).action_approve()

    def test_a_slot_taken_meanwhile_refuses_the_whole_revision(self):
        revision = self.two_department_revision()
        revision.with_user(self.head.user_id).action_approve()
        # Another booking takes the microbiology machine at the new time before its head approves.
        other = self.committed(self.microbiology_way)
        taken = self.booked(other, self.microbiologist)
        taken._set({"starts_at": WEDNESDAY, "ends_at": WEDNESDAY + timedelta(minutes=45)})

        with self.assertRaisesRegex(UserError, "was taken meanwhile"):
            revision.with_user(self.microbiology_head.user_id).action_approve()

        self.assertEqual((revision.status, self.z.starts_at, self.m.starts_at), ("proposed", WEDNESDAY, AFTERNOON))

    def test_rejecting_a_revision_keeps_every_booking_and_the_same_recalculation_is_not_proposed_again(self):
        x_test, x = self.urgent_arrives()
        revision = self.open_revision()

        revision.with_user(self.head.user_id).action_reject()

        self.assertEqual(revision.status, "rejected")
        self.assertEqual((self.z.starts_at, self.y.starts_at), (WEDNESDAY, AFTERNOON))
        # The urgent work stays unplaced with its deadline risk shown.
        self.assertEqual((x.starts_at, x_test.at_risk), (False, True))
        self.env["medilab.machine.booking"]._plan(self.department)
        self.assertFalse(
            self.env[MODEL_PLAN_REVISION].search(
                [("department_id", "=", self.department.id), ("status", "=", "proposed")]
            )
        )
        with self.assertRaisesRegex(UserError, "Only a proposed plan revision"):
            revision.with_user(self.head.user_id).action_approve()

    def test_a_changed_recalculation_is_proposed_after_a_rejection(self):
        self.urgent_arrives()
        rejected = self.open_revision()
        rejected.with_user(self.head.user_id).action_reject()

        # Freeing capacity changes what the recalculation proposes.
        self.record_overtime()

        revision = self.open_revision()
        self.assertNotEqual(revision, rejected)
        self.assertEqual({status for status, _start in self.moves(revision).values()}, {"proposed"})

    def test_a_newer_recalculation_cancels_a_revision_that_was_not_applied(self):
        self.urgent_arrives()
        held = self.open_revision()

        self.record_overtime()

        self.assertEqual(held.status, "cancelled")
        self.assertEqual(self.open_revision().status, "proposed")
