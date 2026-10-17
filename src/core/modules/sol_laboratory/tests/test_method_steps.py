from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .audit_case import AuditLookup
from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_METHOD, MODEL_TESTING_METHOD_STEP


@tagged("post_install", "-at_install")
class TestMethodSteps(AuditLookup, MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spare = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 9997:2026", "name": "Spare method", "field_id": cls.testing_field.id}
        )

    def add_step(self, method=None, **vals):
        return self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": (method or self.method).id,
                "sequence": 1,
                "duration_minutes": 10,
                "instruction": "Weigh the sample.",
                **vals,
            }
        )

    def refusal(self, **vals):
        """The message a user gets when the database refuses the step."""
        with self.assertRaises(IntegrityError) as refused, mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.add_step(**vals)
            self.env.flush_all()
        return self.env[MODEL_TESTING_METHOD_STEP]._sql_error_to_message(refused.exception)

    def test_a_method_lists_its_steps_by_step_number(self):
        self.method.step_ids = [
            Command.create({"sequence": number, "duration_minutes": 5 * number, "instruction": f"Step {number}"})
            for number in (3, 1, 2)
        ]
        self.method.invalidate_recordset(["step_ids"])

        self.assertEqual(self.method.step_ids.mapped("sequence"), [1, 2, 3])
        self.assertEqual(self.method.step_ids.mapped("duration_minutes"), [5, 10, 15])

    def test_two_steps_of_one_method_cannot_have_the_same_number(self):
        self.add_step()

        self.assertEqual(self.refusal(), "Two steps of a testing method cannot have the same number.")
        self.assertEqual(self.add_step(method=self.spare).sequence, 1)

    def test_a_step_needs_a_number_of_at_least_one(self):
        for vals in ({"sequence": False}, {"sequence": 0}, {"sequence": -1}):
            with self.subTest(**vals):
                self.assertEqual(self.refusal(**vals), "A step number must be 1 or more.")

    def test_a_step_takes_at_least_one_minute(self):
        for vals in ({"duration_minutes": False}, {"duration_minutes": 0}, {"duration_minutes": -5}):
            with self.subTest(**vals):
                self.assertEqual(self.refusal(**vals), "A step takes at least one minute.")

    def test_a_step_says_what_to_do(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.add_step(instruction=False)
            self.env.flush_all()
        for blank in ("", "   ", " \n\t "):
            with self.subTest(instruction=blank), self.assertRaises(ValidationError) as refused:
                self.add_step(instruction=blank)
            self.assertEqual(str(refused.exception), "Say what to do in the step.")

    def test_steps_keep_what_was_entered(self):
        step = self.add_step(sequence=7, instruction="  Weigh the sample.\n", note="  ")

        self.assertEqual([step.sequence, step.instruction, step.note], [7, "  Weigh the sample.\n", "  "])

    def test_deleting_an_unused_method_deletes_its_steps(self):
        steps = self.add_step(method=self.spare) | self.add_step(method=self.spare, sequence=2)

        self.spare.unlink()

        self.assertFalse(steps.exists())

    def test_a_method_used_by_a_way_of_testing_keeps_its_steps(self):
        step = self.add_step()

        with self.assertRaises(UserError) as refusal:
            self.method.unlink()

        self.assertIn(self.pair.display_name, str(refusal.exception))
        self.assertTrue(step.exists())

    def test_the_history_of_a_method_shows_the_changes_to_its_steps(self):
        kept, removed = self.add_step(), self.add_step(sequence=2)

        kept.instruction = "Weigh 5 g of the sample."
        removed.unlink()

        history = self.history(self.method, self.new_auditor())
        self.assertIn(self.entries(kept, "create"), history)
        self.assertIn(self.entries(kept, "edit"), history)
        self.assertIn(self.entries(removed, "delete"), history)
        self.assertEqual(
            self.changes(self.entries(kept, "edit"))["instruction"], ("Weigh the sample.", "Weigh 5 g of the sample.")
        )
