from .schedule_invariants_case import WEEKDAYS, ScheduleInvariantsCase

VIETNAM = "Asia/Ho_Chi_Minh"


class LabTimezoneCase(ScheduleInvariantsCase):
    """Working calendars for a laboratory in Vietnam (UTC+7): office hours, and an evening shift worked by a person who
    keeps UTC, so that one working interval spans midnight in Vietnam. A calendar's hours are in its person's time zone.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office_hours = cls.create_calendar(
            "Vietnam office hours", [(day, 8, 12) for day in WEEKDAYS] + [(day, 13, 17) for day in WEEKDAYS]
        )
        cls.utc_evening = cls.create_calendar("Evening shift in UTC", [(day, 15, 19) for day in WEEKDAYS])

    def in_vietnam(self, person, calendar, tz=VIETNAM):
        """Put the laboratory in Vietnam time and the person on the calendar, working it in the time zone."""
        self.env.company.tz = VIETNAM
        person.write({"resource_calendar_id": calendar.id, "tz": tz})

    @classmethod
    def lead_test_expected_on(cls, expected_date):
        """A lead test on a new sample whose request is expected on the date, so its due date is computed from it."""
        request = cls.create_request()
        request.expected_date = expected_date
        return request.sample_ids.test_ids
