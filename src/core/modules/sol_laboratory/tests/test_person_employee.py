from odoo.tests import tagged

from .people_case import PeopleCase


@tagged("post_install", "-at_install")
class TestPersonEmployee(PeopleCase):
    def test_person_is_listed_with_their_department_in_odoos_employees_app(self):
        directory = self.env["hr.employee.public"].with_user(self.microbiologist.user_id)

        listed = directory.search([("department_id", "=", self.chemistry.id)])

        self.assertIn(self.chemist.employee_id.id, listed.ids)

    def test_reader_of_people_reads_the_details_their_employee_holds(self):
        reader = self.create_person("Do Thi Giang", self.chemistry, "giang.do", permissions=["person.read.all"])
        self.chemist.work_email = "an.nguyen@lab.example"
        self.env.invalidate_all()

        [values] = self.as_person(self.chemist, reader).read(["name", "work_email", "department_id"])

        self.assertEqual(
            (values["name"], values["work_email"], values["department_id"][0]),
            ("Nguyen Van An", "an.nguyen@lab.example", self.chemistry.id),
        )

    def test_changing_the_user_in_odoos_employees_app_moves_the_groups(self):
        self.grant(self.chemist, "person.read.all")
        group = self.permissions("person.read.all").group_id
        previous = self.chemist.user_id
        newcomer = self.env["res.users"].create({"login": "an.nguyen.2", "name": "Nguyen Van An"})

        self.chemist.employee_id.user_id = newcomer

        self.assertNotIn(group, previous.group_ids)
        self.assertIn(group, newcomer.group_ids)

    def test_archiving_the_employee_in_odoos_employees_app_archives_the_person_and_their_user(self):
        self.chemist.employee_id.action_archive()

        self.assertFalse(self.chemist.active or self.chemist.user_id.active)

    def test_renaming_the_employee_in_odoos_employees_app_renames_their_contact(self):
        self.chemist.employee_id.name = "Nguyen Van Anh"

        self.assertEqual((self.chemist.name, self.chemist.work_contact_id.name), ("Nguyen Van Anh",) * 2)

    def test_deleting_the_employee_deletes_the_person_and_takes_their_groups_off_the_user(self):
        self.grant(self.chemist, "person.read.all")
        user = self.chemist.user_id

        self.chemist.employee_id.unlink()

        self.assertFalse(self.chemist.exists())
        self.assertEqual(user.group_ids, self.env.ref("base.group_user"))

    def test_deleting_a_person_keeps_their_employee(self):
        employee = self.chemist.employee_id

        self.chemist.unlink()

        self.assertTrue(employee.exists())
