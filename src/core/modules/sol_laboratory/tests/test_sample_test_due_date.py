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

    def test_due_date_is_the_end_of_the_day_the_safety_margin_before_the_expected_date(self):
        # 2 days by default: 2026-10-18 23:59:59 in Vietnam.
        self.assertEqual(self.due_date(), datetime(2026, 10, 18, 16, 59, 59))
        self.env["ir.config_parameter"].set_int(SAFETY_MARGIN_PARAMETER, 3)
        self.assertEqual(self.due_date(), datetime(2026, 10, 17, 16, 59, 59))

    def test_changing_the_safety_margin_leaves_stored_due_dates(self):
        test = self.sample.test_ids
        due_date = test.due_date

        self.env["ir.config_parameter"].set_int(SAFETY_MARGIN_PARAMETER, 5)
        test.invalidate_recordset(["due_date"])
        self.assertEqual(test.due_date, due_date)

    def test_due_date_follows_the_expected_date(self):
        test = self.sample.test_ids

        self.request.expected_date = False
        self.assertFalse(test.due_date)
        self.request.expected_date = "2026-11-10"
        self.assertEqual(test.due_date, datetime(2026, 11, 8, 16, 59, 59))
