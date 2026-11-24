from datetime import datetime

from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.settings import SAFETY_MARGIN_PARAMETER


@tagged("post_install", "-at_install")
class TestSampleTestDueDate(RequestCase):
    def setUp(self):
        super().setUp()
        self.env.company.tz = "Asia/Ho_Chi_Minh"

    def due_date(self):
        return self.create_request().sample_ids.test_ids.due_date

    def test_due_date_is_the_end_of_the_day_the_safety_margin_in_working_days_before_the_committed_date(self):
        # Committed on Tuesday 2026-10-20; 2 working days by default skip the weekend: Friday 23:59:59 in Vietnam.
        self.assertEqual(self.due_date(), datetime(2026, 10, 16, 16, 59, 59))
        self.env["ir.config_parameter"].set_int(SAFETY_MARGIN_PARAMETER, 3)
        self.assertEqual(self.due_date(), datetime(2026, 10, 15, 16, 59, 59))

    def test_changing_the_safety_margin_leaves_stored_due_dates(self):
        test = self.sample.test_ids
        due_date = test.due_date

        self.env["ir.config_parameter"].set_int(SAFETY_MARGIN_PARAMETER, 5)
        test.invalidate_recordset(["due_date"])
        self.assertEqual(test.due_date, due_date)

    def test_due_date_follows_the_committed_date(self):
        test = self.sample.test_ids

        self.request.committed_date = False
        self.assertFalse(test.due_date)
        self.request.committed_date = "2026-11-10"
        self.assertEqual(test.due_date, datetime(2026, 11, 6, 16, 59, 59))
