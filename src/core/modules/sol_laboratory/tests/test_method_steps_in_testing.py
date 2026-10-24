from datetime import timedelta

from freezegun import freeze_time
from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestMethodStepsInTesting(SchedulingCase):
    """A person who runs a test without reading sample tests, on a method with three steps entered out of order."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner = cls.create_person("Vo Thi Giang", cls.department, "giang.vo")
        cls.runner.tz = "UTC"
        cls.steps = cls.env[MODEL_TESTING_METHOD_STEP].create(
            [
                {"method_id": cls.method.id, "sequence": number, "duration_minutes": minutes, "instruction": text}
                for number, minutes, text in (
                    (2, 480, "Ash the test portion."),
                    (1, 15, "Weigh the test portion."),
                    (3, 30, "Dissolve the ash and make up to volume."),
                )
            ]
        )
        cls.steps[0].note = "Raise the temperature gradually."
        cls.stepless = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 9996:2026", "name": "Lead by ICP-MS", "field_id": cls.testing_field.id}
        )

    def run_test(self, way=None):
        """A test with its way of testing chosen, its testing task assigned to the runner and a booking for them."""
        test = self.new_test()
        test.parameter_method_id = way or self.pair
        task = self.testing_task(test, self.runner)
        booking = self.env[MODEL_MACHINE_BOOKING].create(
            {
                "machine_id": self.fast.id,
                "sample_test_id": test.id,
                "task_id": task.id,
                "person_id": self.runner.id,
            }
        )
        return test, task, booking

    def seen(self, records, person):
        """The steps the person sees on the records in a new request, as number, minutes, instruction and note."""
        self.env.invalidate_all()
        return [
            [(step.sequence, step.duration_minutes, step.instruction, step.note) for step in record.method_step_ids]
            for record in self.as_person(records, person)
        ]

    def test_the_runner_sees_the_steps_of_the_method_in_step_number_order(self):
        test, task, booking = self.run_test()
        expected = [
            (1, 15, "Weigh the test portion.", False),
            (2, 480, "Ash the test portion.", "Raise the temperature gradually."),
            (3, 30, "Dissolve the ash and make up to volume.", False),
        ]

        self.assertEqual(self.seen(task, self.runner), [expected])
        self.assertEqual(self.seen(booking, self.runner), [expected])
        with self.assertRaises(AccessError):
            self.as_person(test, self.runner).read(["parameter_method_id"])

    def test_every_way_of_testing_of_the_method_shows_the_same_steps(self):
        cadmium = self.create_parameter("Cadmium (Cd)", self.group)
        other_way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cadmium.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
            }
        )
        _lead, lead_task, lead_booking = self.run_test()
        _cadmium, cadmium_task, cadmium_booking = self.run_test(other_way)

        seen = self.seen(lead_task | cadmium_task, self.runner) + self.seen(lead_booking | cadmium_booking, self.runner)

        self.assertEqual(len(seen[0]), 3)
        self.assertEqual(seen, [seen[0]] * 4)

    def test_a_method_without_steps_shows_none(self):
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.stepless.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
            }
        )
        _test, task, booking = self.run_test(way)

        self.assertEqual(self.seen(task, self.runner) + self.seen(booking, self.runner), [[], []])

    def test_a_test_without_a_way_of_testing_shows_no_steps(self):
        task = self.testing_task(self.new_test(), self.runner)

        self.assertEqual(self.seen(task, self.runner), [[]])

    def test_other_tasks_show_no_steps(self):
        test, _task, _booking = self.run_test()
        general = self.env.ref("sol_laboratory.task_type_general")
        values = {"type_id": general.id, "assignee_id": self.runner.id, "deadline": MONDAY + timedelta(days=1)}
        tasks = self.env[MODEL_TASK].create(
            [
                {**values, "name": "Calibrate the balance"},
                {**values, "name": "Review the test", "document_model": MODEL_SAMPLE_TEST, "document_id": test.id},
            ]
        )

        self.assertEqual(self.seen(tasks, self.runner), [[], []])

    def test_a_task_whose_test_is_gone_shows_no_steps(self):
        task = self.testing_task(self.new_test(), self.runner)
        missing = max(self.env[MODEL_SAMPLE_TEST].search([]).ids) + 1000
        task.document_id = missing

        self.assertEqual(self.seen(task, self.runner), [[]])

    def test_changing_the_steps_shows_on_existing_tasks_and_bookings(self):
        _test, task, booking = self.run_test()
        first, second, third = self.steps.sorted("sequence")

        first.instruction = "Weigh 5 g of the test portion."
        third.unlink()
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {"method_id": self.method.id, "sequence": 4, "duration_minutes": 20, "instruction": "Measure."}
        )

        expected = [(1, "Weigh 5 g of the test portion."), (2, second.instruction), (4, "Measure.")]
        # The booking follows its dependencies at once; the task reads its test anew on the next request.
        self.assertEqual([(step.sequence, step.instruction) for step in booking.method_step_ids], expected)
        for seen in self.seen(task, self.runner) + self.seen(booking, self.runner):
            self.assertEqual([(number, instruction) for number, _minutes, instruction, _note in seen], expected)

    def test_switching_the_way_of_testing_shows_the_steps_of_the_new_method(self):
        test, task, booking = self.run_test()
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {"method_id": self.stepless.id, "sequence": 1, "duration_minutes": 60, "instruction": "Run the ICP-MS."}
        )
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.stepless.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
            }
        )

        test.parameter_method_id = way

        self.assertEqual(booking.method_step_ids, self.stepless.step_ids)
        self.assertEqual(
            self.seen(task, self.runner) + self.seen(booking, self.runner), [[(1, 60, "Run the ICP-MS.", False)]] * 2
        )

    def test_no_one_changes_a_step_through_a_task_or_a_booking(self):
        _test, task, booking = self.run_test()
        step = self.steps.sorted("sequence")[0]
        new_step = {"method_id": self.method.id, "sequence": 9, "duration_minutes": 5, "instruction": "Clean up."}
        for person in (self.runner, self.head):
            for record in (task, booking):
                with self.subTest(person=person.name, model=record._name), self.assertRaises(AccessError):
                    self.as_person(record, person).write(
                        {"method_step_ids": [Command.update(step.id, {"instruction": "Changed."})]}
                    )
        for command in (Command.create(new_step), Command.delete(step.id)):
            with self.subTest(command=command[0]), self.assertRaises(AccessError):
                self.as_person(task, self.head).write({"method_step_ids": [command]})
            self.as_person(booking, self.head).write({"method_step_ids": [command]})

        self.env.invalidate_all()
        self.assertEqual(self.method.step_ids, self.steps)
        self.assertEqual(step.instruction, "Weigh the test portion.")

    def test_the_steps_are_read_only_on_tasks_and_bookings(self):
        for model in (MODEL_TASK, MODEL_MACHINE_BOOKING):
            records = self.env[model].with_user(self.runner.user_id)
            with self.subTest(model=model):
                self.assertTrue(records.fields_get(["method_step_ids"], ["readonly"])["method_step_ids"]["readonly"])
                form = etree.fromstring(records.get_views([(False, "form")])["views"]["form"]["arch"])
                [field] = form.iterfind(".//field[@name='method_step_ids']")
                [steps] = field.iterfind("list")
                self.assertEqual(field.get("readonly"), "1")
                self.assertEqual([steps.get(flag) for flag in ("create", "delete", "edit")], ["0"] * 3)
                self.assertEqual(
                    [column.get("name") for column in steps.iterfind("field")],
                    ["sequence", "duration_minutes", "instruction", "location_id", "note"],
                )

    def test_the_administrator_edits_steps_on_the_method_form(self):
        administrator = self.env.ref("base.user_admin")
        methods = self.env[MODEL_TESTING_METHOD]

        form = etree.fromstring(methods.with_user(administrator).get_views([(False, "form")])["views"]["form"]["arch"])
        [steps] = form.iterfind(".//field[@name='step_ids']/list")
        self.assertEqual(steps.get("editable"), "bottom")
        self.assertEqual(
            [column.get("name") for column in steps.iterfind("field")],
            ["sequence", "duration_minutes", "instruction", "location_id", "note"],
        )
        self.assertIsNone(form.get("edit"))
        tester_form = methods.with_user(self.runner.user_id).get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertEqual(etree.fromstring(tester_form).get("edit"), "False")
