from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import tagged

from .people_case import PeopleCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_SAMPLE_TEST_DUE_DATE_CHANGE

# Friday 16 October 2026 at 10:00 in Vietnam, and the Saturday after it.
FRIDAY = datetime(2026, 10, 16, 3, 0, 0)
SATURDAY = datetime(2026, 10, 17, 3, 0, 0)
REASON = "The AAS is serviced on the 18th."


@tagged("post_install", "-at_install")
class TestSampleTestDueDateChange(RequestCase, PeopleCase):
    """The head of Analytical chemistry, which tests the lead sample, changes the due date of its test."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test = cls.sample.test_ids
        cls.head = cls.create_person("Le Thi Hoa", cls.department, "hoa.head", permissions=("sample_test_read_all",))
        cls.department.manager_id = cls.head.employee_id
        cls.tester = cls.create_person(
            "Pham Van Nam", cls.department, "nam.pham", permissions=("sample_test_read_all", "sample_test_edit_all")
        )
        cls.other_head = cls.create_person(
            "Do Thi Giang", cls.microbiology, "giang.do", permissions=("sample_test_read_all",)
        )
        cls.microbiology.manager_id = cls.other_head.employee_id

    def setUp(self):
        super().setUp()
        self.env.company.tz = "Asia/Ho_Chi_Minh"

    def change(self, person, due_date, reason=REASON):
        self.wizard(person, due_date, reason).action_change()

    def wizard(self, person, due_date, reason=REASON):
        return (
            self.env[MODEL_SAMPLE_TEST_DUE_DATE_CHANGE]
            .with_user(person.user_id)
            .create({"sample_test_id": self.test.id, "due_date": due_date, "reason": reason})
        )

    def test_the_head_changes_the_due_date_with_a_reason(self):
        self.change(self.head, FRIDAY)

        self.assertEqual((self.test.due_date, self.test.due_date_reason), (FRIDAY, REASON))

    def test_only_the_head_changes_the_due_date_and_only_with_a_reason(self):
        before = self.test.due_date
        for person, reason in ((self.tester, REASON), (self.other_head, REASON), (self.head, " ")):
            with self.subTest(person=person.name, reason=reason), self.assertRaises(UserError):
                self.change(person, FRIDAY, reason)
        for field, value in (("due_date", FRIDAY), ("due_date_reason", REASON)):
            with self.subTest(field=field), self.assertRaises(UserError):
                self.test.with_user(self.tester.user_id).write({field: value})
        self.assertEqual((self.test.due_date, self.test.due_date_reason), (before, False))

        self.change(self.head, FRIDAY)
        with self.assertRaises(UserError):
            self.test.with_user(self.tester.user_id).action_clear_due_date()
        self.assertEqual(self.test.due_date_reason, REASON)

    def test_a_changed_due_date_stays_when_the_expected_date_changes_and_automatic_ones_follow_it(self):
        cadmium = self.create_parameter("Cadmium (Cd)", self.group)
        self.offer(cadmium, self.sample_type)
        automatic = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": cadmium.id})
        self.change(self.head, FRIDAY)

        self.request.expected_date = "2026-11-10"
        self.assertEqual(self.test.due_date, FRIDAY)
        # 2026-11-08 23:59:59 in Vietnam.
        self.assertEqual(automatic.due_date, datetime(2026, 11, 8, 16, 59, 59))
        self.assertFalse(self.test.due_date_conflict)

        # The expected date now gives 2026-10-15 23:59:59 in Vietnam, before the changed date.
        self.request.expected_date = "2026-10-17"
        self.assertEqual(self.test.due_date, FRIDAY)
        self.assertTrue(self.test.with_user(self.head.user_id).due_date_conflict)
        self.assertFalse(automatic.due_date_conflict)

    def test_the_head_goes_back_to_the_automatic_due_date(self):
        self.change(self.head, FRIDAY)

        self.test.with_user(self.head.user_id).action_clear_due_date()

        # 2026-10-18 23:59:59 in Vietnam.
        self.assertEqual((self.test.due_date, self.test.due_date_reason), (datetime(2026, 10, 18, 16, 59, 59), False))

    def test_a_non_working_day_is_reported_and_a_holiday_counted_as_working_time_is_accepted(self):
        self.assertFalse(self.wizard(self.head, FRIDAY).due_on_non_working_day)
        self.assertTrue(self.wizard(self.head, SATURDAY).due_on_non_working_day)
        holiday = self.env["resource.calendar.leaves"].create(
            {"name": "Public holiday", "date_from": datetime(2026, 10, 15, 17, 0, 0), "date_to": SATURDAY}
        )
        self.change(self.head, FRIDAY)
        self.assertTrue(self.test.due_on_non_working_day)

        holiday.count_as = "working_time"
        self.assertFalse(self.wizard(self.head, FRIDAY).due_on_non_working_day)
        self.test.invalidate_recordset(["due_on_non_working_day"])
        self.assertFalse(self.test.due_on_non_working_day)
