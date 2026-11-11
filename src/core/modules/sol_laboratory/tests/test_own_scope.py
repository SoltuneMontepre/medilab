from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_PERSON, MODEL_ROLE


@tagged("post_install", "-at_install")
class TestOwnScope(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.read_own, cls.edit_own = cls.env[MODEL_PERMISSION].create(
            [
                {"name": f"{action} own person", "document_model": MODEL_PERSON, "action": action, "scope": "own"}
                for action in ("read", "edit")
            ]
        )
        cls.owner = cls.create_person("Do Thi Giang", cls.chemistry, "giang.do")
        cls.owner.permission_ids = cls.read_own
        cls.people = cls.as_person(cls.env[MODEL_PERSON], cls.owner)

    def test_only_the_records_of_the_user_are_listed(self):
        self.assertEqual(self.people.search([]), self.owner)

    def test_another_persons_record_cannot_be_read(self):
        with self.assertRaises(AccessError):
            self.as_person(self.chemist, self.owner).read(["name"])

    def test_editing_is_limited_to_the_own_records(self):
        self.owner.permission_ids |= self.edit_own

        self.as_person(self.owner, self.owner).write({"phone": "0912 345 678"})
        self.assertEqual(self.owner.phone, "0912 345 678")
        with self.assertRaises(AccessError):
            self.as_person(self.chemist, self.owner).write({"phone": "0912 345 678"})

    def test_own_needs_a_user_on_the_document_type(self):
        with self.assertRaisesRegex(ValidationError, "has no user"):
            self.env[MODEL_PERMISSION].create(
                {"name": "Read own roles", "document_model": MODEL_ROLE, "action": "read", "scope": "own"}
            )

    def test_own_access_limits_records_to_the_users_own(self):
        permission = self.env[MODEL_PERMISSION].new({"document_model": MODEL_PERSON, "action": "read", "scope": "own"})

        self.assertEqual(permission._access_values()["domain"], "[('user_id', '=', user.id)]")
