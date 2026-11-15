from odoo.tests import tagged

from .schedule_race_case import ScheduleRaceCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_MACHINE_METHOD


@tagged("post_install", "-at_install")
class TestSharedCapacityRaces(ScheduleRaceCase):
    def _race_capacity_change(self, commits_first):
        def prepare(env):
            link = env[MODEL_MACHINE_METHOD].search([("machine_id", "=", self.machine_id)])
            link.capacity = 2
            self.assign(env, 0)
            self.assign(env, 1)
            return link.id

        link_id = self.committed(prepare)
        self.committed(self.schedule(0))

        def reduce_capacity(env):
            link = env[MODEL_MACHINE_METHOD].browse(link_id)
            self.assertEqual(link.capacity, 2)
            link.write({"capacity": 1})

        outcomes = self.race(
            reduce_capacity,
            self.schedule(1),
            boundaries={
                "first": (
                    MODEL_MACHINE_METHOD,
                    "write",
                    lambda links, args: links.ids == [link_id] and args[0].get("capacity") == 1,
                ),
                "second": self.placing(1),
            },
            commits_first=commits_first,
        )

        def occupied(env):
            bookings = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.test_ids)])
            self.assertEqual(len(bookings), 2)
            return env[MODEL_MACHINE_METHOD].browse(link_id).capacity, {
                (booking.starts_at, booking.ends_at) for booking in bookings
            }

        return outcomes, self.committed(occupied)

    def test_capacity_reduction_commits_before_a_booking_joins(self):
        outcomes, (capacity, intervals) = self._race_capacity_change("first")

        self.assertEqual(
            {name: status for name, (status, _result) in outcomes.items()}, dict.fromkeys(outcomes, "committed")
        )
        self.assertEqual(capacity, 1)
        self.assertEqual(len(intervals), 2)
        self.assert_retried_on_conflict("second")

    def test_booking_joins_before_capacity_reduction_commits(self):
        outcomes, (capacity, intervals) = self._race_capacity_change("second")

        self.assertEqual(outcomes["first"][0], "refused")
        self.assertIn("capacity", outcomes["first"][1])
        self.assertEqual(outcomes["second"][0], "committed")
        self.assertEqual(capacity, 2)
        self.assertEqual(len(intervals), 1)
        self.assert_retried_on_conflict("first")
