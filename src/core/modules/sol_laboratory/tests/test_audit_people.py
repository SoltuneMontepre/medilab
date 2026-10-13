from odoo.tests import new_test_user, tagged

from .audit_case import AUDITOR_GROUPS, AuditLookup
from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT


@tagged("post_install", "-at_install")
class TestAuditPeople(AuditLookup, PeopleCase):
    def test_a_department_is_audited(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Physical chemistry"})

        department.name = "Physicochemistry"

        self.assertEqual(
            self.changes(self.entries(department, "edit")), {"name": ("Physical chemistry", "Physicochemistry")}
        )

    def test_the_department_of_a_person_is_recorded_once_on_their_employee(self):
        employee = self.chemist.employee_id
        earlier = self.entries(employee) | self.entries(self.chemist)

        self.chemist.department_id = self.microbiology

        self.assertEqual(
            self.changes(self.entries(employee) - earlier)["department_id"],
            (f"Chemistry (#{self.chemistry.id})", f"Microbiology (#{self.microbiology.id})"),
        )
        self.assertFalse(self.entries(self.chemist) - earlier)

    def test_the_history_of_a_person_includes_their_employee(self):
        auditor = new_test_user(self.env, login="auditor", groups=AUDITOR_GROUPS)
        self.chemist.employee_id.job_title = "Senior chemist"

        history = self.history(self.chemist, auditor)

        self.assertLessEqual(self.entries(self.chemist.employee_id), history)
        self.assertFalse(history & self.entries(self.microbiologist.employee_id))

    def test_the_private_details_of_an_employee_are_masked(self):
        employee = self.chemist.employee_id
        earlier = self.entries(employee)

        employee.private_phone = "0901 234 567"

        self.assertEqual(self.changes(self.entries(employee) - earlier), {"private_phone": (False, "***")})
