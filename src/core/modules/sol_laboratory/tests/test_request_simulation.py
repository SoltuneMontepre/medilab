from datetime import date, timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK, MODEL_TASK_TYPE, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE


@tagged("post_install", "-at_install")
@freeze_time(MONDAY)
class TestRequestSimulation(SchedulingCase):
    """On Monday at 08:00, the fast machine runs lead in 45 minutes and the slow one in 75, each with one tester."""

    def setUp(self):
        super().setUp()
        self.env.company.tz = "UTC"
        self.requests = self.env[MODEL_TEST_REQUEST]

    def held_request(self):
        """A paid request whose lead sample has not arrived yet."""
        request = self.create_request()
        request.sudo().status = "paid"
        return request

    def test_the_whole_order_competes_for_the_same_machines(self):
        # Alone each test would finish at 08:45; together the third waits for the fast machine.
        simulated = self.requests._simulate_ways([self.pair] * 3, MONDAY)

        self.assertEqual(simulated["finish"], MONDAY + timedelta(minutes=90))
        self.assertFalse(simulated["missing"])

    def test_expected_tests_of_confirmed_requests_hold_their_place(self):
        self.held_request()

        simulated = self.requests._simulate_ways([self.pair], MONDAY)

        self.assertEqual(simulated["finish"], MONDAY + timedelta(minutes=75))

    def test_held_work_waits_for_its_collection_appointment(self):
        request = self.held_request()
        task_type = self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        self.env[MODEL_TASK].sudo().create(
            {
                "type_id": task_type.id,
                "name": "Collect lead",
                "document_model": request._name,
                "document_id": request.id,
                "deadline": MONDAY + timedelta(days=1),
                "planned_start": MONDAY + timedelta(days=1),
            }
        )

        simulated = self.requests._simulate_ways([self.pair], MONDAY)

        self.assertEqual(simulated["finish"], MONDAY + timedelta(minutes=45))

    def test_the_simulation_books_nothing(self):
        self.held_request()
        bookings = self.env["medilab.machine.booking"].search_count([])

        self.requests._simulate_ways([self.pair] * 2, MONDAY)

        self.assertEqual(self.env["medilab.machine.booking"].search_count([]), bookings)

    def test_the_earliest_return_adds_the_margin_in_working_days(self):
        # Finished on Monday, plus 2 working days.
        earliest = self.requests._earliest_return([self.pair], MONDAY, 0)

        self.assertEqual(earliest["date"], date(2026, 10, 14))

    def test_the_standard_turnaround_is_the_least_the_estimate_gives(self):
        earliest = self.requests._earliest_return([self.pair], MONDAY, 5)

        self.assertEqual(earliest["date"], date(2026, 10, 19))

    def test_the_margin_counts_working_days_back_over_a_weekend(self):
        self.assertEqual(self.requests._working_days_before(date(2026, 10, 20), 2), date(2026, 10, 16))
