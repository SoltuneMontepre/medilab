from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .location_case import LocationCase
from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK, MODEL_TESTING_METHOD_STEP

RO_01 = "A-RO1 RO water sampling point 1"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestLocationsInTesting(SchedulingCase, LocationCase):
    """The lead method's first step is done at the water point, and the sample was taken from A-RO1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.water_point = cls.create_location("A-WP1", "Deionised water point", cls.floor, map_x=0.2, map_y=0.9)
        cls.env[MODEL_TESTING_METHOD_STEP].create(
            [
                {
                    "method_id": cls.method.id,
                    "sequence": 1,
                    "duration_minutes": 15,
                    "instruction": "Make the standards up to volume.",
                    "location_id": cls.water_point.id,
                },
                {"method_id": cls.method.id, "sequence": 2, "duration_minutes": 40, "instruction": "Measure."},
            ]
        )
        cls.sample.sampling_location_id = cls.sampling_point
        cls.test.parameter_method_id = cls.pair

    def tester_task(self, test=None):
        task = self.testing_task(test or self.test, self.tester)
        self.env.invalidate_all()
        return self.as_person(task, self.tester)

    def test_a_step_with_a_location_shows_its_code_and_name_to_the_tester(self):
        task = self.tester_task()

        self.assertEqual(
            [step.location_id.display_name or "" for step in task.method_step_ids], ["A-WP1 Deionised water point", ""]
        )

    def test_a_testing_task_shows_the_location_its_sample_was_taken_from(self):
        task = self.tester_task()
        tasks = self.as_person(self.env[MODEL_TASK], self.tester)

        self.assertEqual(task.sampling_location_id, self.sampling_point)
        self.assertEqual(
            tasks.search_read([("id", "=", task.id)], ["sampling_location_id"])[0]["sampling_location_id"],
            (self.sampling_point.id, RO_01),
        )
        self.assertEqual(tasks.get_dashboard_data()["next_up"][0]["location"], RO_01)
        booking = self.schedule(self.test, self.tester)
        self.assertEqual(booking.calendar_event_id.location, RO_01)

    def test_a_planned_testing_task_shows_the_location_on_its_calendar_event(self):
        task = self.tester_task()

        task.sudo().write({"planned_start": MONDAY, "planned_end": MONDAY + timedelta(hours=1)})

        event = self.env["calendar.event"].search([("medilab_task_id", "=", task.id)])
        self.assertEqual(event.location, RO_01)
        self.assertEqual(
            self.as_person(self.env[MODEL_TASK], self.tester).get_dashboard_data()["planned_today"][0]["location"],
            RO_01,
        )

    def test_opening_the_location_shows_it_on_its_parents_map(self):
        location = self.as_person(self.tester_task().sampling_location_id, self.tester)

        floor_map = location.parent_id.get_map()

        self.assertTrue(floor_map["image_id"])
        self.assertIn({"id": location.id, "code": "A-RO1", "name": RO_01, "x": 0.2, "y": 0.7}, floor_map["points"])

    def test_other_tasks_show_no_location(self):
        unlocated = self.new_test()
        general = self.env.ref("sol_laboratory.task_type_general")
        manual = self.env[MODEL_TASK].create(
            {
                "type_id": general.id,
                "name": "Calibrate the balance",
                "assignee_id": self.tester.id,
                "deadline": MONDAY + timedelta(days=1),
            }
        )

        for task in (self.tester_task(unlocated), self.as_person(manual, self.tester)):
            with self.subTest(task=task.name):
                self.assertFalse(task.sampling_location_id)
