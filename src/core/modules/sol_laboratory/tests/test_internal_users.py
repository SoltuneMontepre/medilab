from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_EMPLOYEE, MODEL_PERSON, MODEL_RES_USERS, MODEL_USER_LINK
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_ROLE


@tagged("post_install", "-at_install")
class TestInternalUsers(PeopleCase):
    """An administrator who signs in, an internal user no person links to and a portal user."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.create_person("Pham Van Dung", login="dung.pham", roles=cls.env.ref(ADMINISTRATOR_ROLE))
        users = cls.env[MODEL_RES_USERS].with_context(no_reset_password=True)
        cls.unlinked = users.create({"login": "hung.trinh", "name": "Trinh Van Hung"})
        cls.portal = users.create(
            {
                "login": "lan.portal",
                "name": "Le Thi Lan",
                "group_ids": [Command.set(cls.env.ref("base.group_portal").ids)],
            }
        )

    def as_administrator(self, records):
        return records.with_user(self.administrator.user_id)

    def link(self, user, person=None):
        wizard = self.as_administrator(self.env[MODEL_USER_LINK]).create(
            {"user_id": user.id, "person_id": person.id if person else False}
        )
        wizard.action_link()

    def test_administrator_cannot_create_an_internal_user(self):
        users = self.as_administrator(self.env[MODEL_RES_USERS]).with_context(no_reset_password=True)

        with self.assertRaisesRegex(UserError, "only through a person"):
            users.create({"login": "khoa.do", "name": "Do Van Khoa"})
        with self.assertRaisesRegex(UserError, "only through a person"):
            self.as_administrator(self.unlinked).copy()

    def test_administrator_still_creates_portal_users(self):
        users = self.as_administrator(self.env[MODEL_RES_USERS]).with_context(no_reset_password=True)

        user = users.create(
            {
                "login": "mai.portal",
                "name": "Ngo Thi Mai",
                "group_ids": [Command.set(self.env.ref("base.group_portal").ids)],
            }
        )

        self.assertTrue(user.share)

    def test_administrator_cannot_make_a_portal_user_internal(self):
        internal, portal = self.env.ref("base.group_user"), self.env.ref("base.group_portal")

        with self.assertRaisesRegex(UserError, "only through a person"):
            self.as_administrator(self.portal).write(
                {"group_ids": [Command.unlink(portal.id), Command.link(internal.id)]}
            )
        # Taken out of the portal group first, the user is added to the internal one from the group.
        self.as_administrator(portal).write({"user_ids": [Command.unlink(self.portal.id)]})
        with self.assertRaisesRegex(UserError, "only through a person"):
            self.as_administrator(internal).write({"user_ids": [Command.link(self.portal.id)]})
        self.assertTrue(self.portal.share)

    def test_administrator_creates_an_internal_user_by_giving_a_person_a_login(self):
        person = self.as_administrator(self.env[MODEL_PERSON]).create({"name": "Do Van Khoa", "login": "khoa.do"})

        self.assertTrue(person.user_id._is_internal())

    def test_employee_invitation_creates_no_user(self):
        employee = self.as_administrator(self.env[MODEL_EMPLOYEE]).create(
            {"name": "Do Van Khoa", "work_email": "khoa.do@lab.example"}
        )

        with self.assertRaisesRegex(UserError, "created from people"):
            employee.action_send_invitation()
        self.assertFalse(employee.user_id)

    def test_internal_users_without_a_person_are_listed(self):
        unlinked = self.env[MODEL_RES_USERS].search([("share", "=", False), ("has_person", "=", False)])

        self.assertIn(self.unlinked, unlinked)
        self.assertNotIn(self.chemist.user_id, unlinked)
        self.assertNotIn(self.portal, unlinked)
        self.assertFalse(self.unlinked.has_person)
        self.assertTrue(self.chemist.user_id.has_person)

    def test_an_archived_persons_user_is_not_listed(self):
        self.chemist.action_archive()

        unlinked = self.env[MODEL_RES_USERS].with_context(active_test=False).search([("has_person", "=", False)])
        self.assertNotIn(self.chemist.user_id, unlinked)

    def test_linking_without_a_person_creates_one_from_the_user(self):
        self.link(self.unlinked)

        person = self.env[MODEL_PERSON].search([("user_id", "=", self.unlinked.id)])
        self.assertEqual(person.name, "Trinh Van Hung")
        self.assertEqual(person.work_contact_id, self.unlinked.partner_id)
        self.assertTrue(self.unlinked.has_person)

    def test_linking_to_a_person_without_a_login_gives_them_the_user(self):
        person = self.create_person("Trinh Van Hung", self.chemistry, roles=self.env.ref(ADMINISTRATOR_ROLE))

        self.link(self.unlinked, person)

        self.assertEqual(person.user_id, self.unlinked)
        self.assertIn(self.env.ref(ADMINISTRATOR_ROLE).group_id, self.unlinked.group_ids)

    def test_a_user_with_an_employee_is_linked_by_creating_a_person_from_it(self):
        employee = self.env[MODEL_EMPLOYEE].create({"name": "Trinh Van Hung", "user_id": self.unlinked.id})
        person = self.create_person("Trinh Van Hung", self.chemistry)

        with self.assertRaisesRegex(UserError, "already has the employee"):
            self.link(self.unlinked, person)
        self.link(self.unlinked)

        self.assertEqual(self.env[MODEL_PERSON].search([("user_id", "=", self.unlinked.id)]).employee_id, employee)

    def test_a_linked_user_cannot_be_linked_again(self):
        person = self.create_person("Trinh Van Hung", self.chemistry)

        with self.assertRaisesRegex(UserError, "already linked"):
            self.link(self.chemist.user_id, person)

    def test_administrator_archives_an_unlinked_user(self):
        self.as_administrator(self.unlinked).action_archive()

        self.assertFalse(self.unlinked.active)
