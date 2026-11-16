from ast import literal_eval
from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .scheduling_case import SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_RESOURCE_CALENDAR_LEAVES

# Saturday 17 October 2026 in Vietnam.
HOLIDAY_START = datetime(2026, 10, 16, 17, 0, 0)
HOLIDAY_END = datetime(2026, 10, 17, 16, 59, 59)


@tagged("post_install", "-at_install")
class TestPublicHolidays(SchedulingCase):
    """The administrator keeps the public holidays on the company calendar and marks one the laboratory works on."""

    def test_the_administrator_marks_a_public_holiday_as_a_working_day_and_nobody_else_changes_it(self):
        holiday = self.env[MODEL_RESOURCE_CALENDAR_LEAVES].create(
            {"name": "Public holiday", "date_from": HOLIDAY_START, "date_to": HOLIDAY_END}
        )
        self.assertEqual(holiday.count_as, "absence")

        with self.assertRaises(AccessError):
            holiday.with_user(self.head.user_id).write({"count_as": "working_time"})
        holiday.with_user(self.env.ref("base.user_admin")).write({"count_as": "working_time"})

        self.assertEqual(holiday.count_as, "working_time")

    def test_the_public_holidays_menu_is_for_administrators_and_lists_company_wide_time_off(self):
        menu = self.env.ref("sol_laboratory.menu_public_holiday")
        action = self.env.ref("sol_laboratory.action_medilab_public_holiday")
        own_leave = self.env[MODEL_RESOURCE_CALENDAR_LEAVES].create(
            {
                "name": "Annual leave",
                "resource_id": self.tester.resource_id.id,
                "date_from": HOLIDAY_START,
                "date_to": HOLIDAY_END,
            }
        )
        holiday = self.env[MODEL_RESOURCE_CALENDAR_LEAVES].create(
            {"name": "Public holiday", "date_from": HOLIDAY_START, "date_to": HOLIDAY_END}
        )

        listed = self.env[MODEL_RESOURCE_CALENDAR_LEAVES].search(literal_eval(action.domain))

        self.assertEqual(menu.group_ids, self.env.ref("base.group_system"))
        self.assertIn(holiday, listed)
        self.assertNotIn(own_leave, listed)
