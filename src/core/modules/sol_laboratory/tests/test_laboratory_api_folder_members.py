from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    INVALID_REQUEST,
    LOCKED,
    NOT_ELIGIBLE,
    NOT_FOUND,
    OWNER_ROLE,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER_MEMBER
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP


@tagged("post_install", "-at_install")
class TestLaboratoryApiFolderMembers(LaboratoryApiCase):
    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "tester-installation")
        self.members_key = self.signed_in_key(self.member, "members-installation")
        self.administrators_key = self.signed_in_key(self.administrator, "administrators-installation")
        self.path = f"/folders/{self.folder.id}/members"

    def add(self, user, key=None):
        return self.api("POST", self.path, {"user_id": user.id}, key=key or self.key)

    def row_of(self, user):
        return self.env[MODEL_LABORATORY_FOLDER_MEMBER].search(
            [("folder_id", "=", self.folder.id), ("user_id", "=", user.id)]
        )

    def candidates(self, query, key=None):
        return self.api("GET", f"/folders/{self.folder.id}/member-candidates?q={query}", key=key or self.key)

    def test_members_read_the_members_of_their_folder_its_owner_first(self):
        members = self.api("GET", self.path, key=self.members_key).json()["members"]

        self.assertEqual(
            [(member["user"]["id"], member["role"]) for member in members],
            [(self.tester.id, "owner"), (self.member.id, "member")],
        )
        self.assertApiRefused(NOT_FOUND, self.api("GET", self.path, key=self.signed_in_key(self.outsider, "pc")))

    def test_the_owner_adds_a_member_and_adding_them_again_finds_them(self):
        first = self.add(self.outsider)
        again = self.add(self.outsider)

        self.assertEqual(first.json(), again.json())
        self.assertEqual(first.json()["member"]["role"], "member")
        self.assertEqual(len(self.row_of(self.outsider)), 1)

    def test_administrators_add_members_to_a_folder_they_are_not_a_member_of(self):
        self.assertEqual(self.add(self.outsider, self.administrators_key).status_code, 200)

    def test_a_member_who_does_not_own_the_folder_adds_and_removes_nobody(self):
        self.assertApiRefused(PERMISSION_DENIED, self.add(self.outsider, self.members_key))
        removed = self.api("DELETE", f"{self.path}/{self.row_of(self.tester).id}", key=self.members_key)
        self.assertApiRefused(PERMISSION_DENIED, removed)

    def test_a_person_who_cannot_be_a_member_is_refused_with_one_answer(self):
        inactive = self.create_user("lab.inactive", LABORATORY_FILES_GROUP)
        inactive.active = False
        answers = {self.add(user).json()["error"]["message"] for user in (self.colleague, inactive)}

        self.assertApiRefused(NOT_ELIGIBLE, self.add(self.colleague))
        self.assertEqual(len(answers), 1)
        for user_id in (0, 999999):
            with self.subTest(user_id=user_id):
                self.assertApiRefused(NOT_ELIGIBLE, self.api("POST", self.path, {"user_id": user_id}, key=self.key))

    def test_removing_a_member_twice_has_the_effect_of_once(self):
        row = self.row_of(self.member)

        self.assertEqual(self.api("DELETE", f"{self.path}/{row.id}", key=self.key).status_code, 204)
        self.assertEqual(self.api("DELETE", f"{self.path}/{row.id}", key=self.key).status_code, 204)
        self.assertFalse(self.row_of(self.member))

    def test_the_owner_is_never_removed(self):
        removed = self.api("DELETE", f"{self.path}/{self.row_of(self.tester).id}", key=self.administrators_key)

        self.assertApiRefused(INVALID_REQUEST, removed)
        self.assertEqual(self.row_of(self.tester).role, OWNER_ROLE)

    def test_the_members_of_a_folder_someone_else_is_editing_do_not_change_meanwhile(self):
        self.folder.with_user(self.administrator).lock_take()

        self.assertApiRefused(LOCKED, self.add(self.outsider))

    def test_the_members_of_an_archived_folder_do_not_change(self):
        self.folder.with_user(self.administrator).action_archive_folder()

        self.assertApiRefused(FOLDER_ARCHIVED, self.add(self.outsider))
        removed = self.api("DELETE", f"{self.path}/{self.row_of(self.member).id}", key=self.key)
        self.assertApiRefused(FOLDER_ARCHIVED, removed)

    def test_the_owner_finds_the_people_they_can_add_by_part_of_a_name_or_login(self):
        self.create_user("lab.other", LABORATORY_FILES_GROUP)
        found = self.candidates("lab.").json()["candidates"]

        self.assertEqual({user["login"] for user in found}, {"lab.outsider", "lab.administrator", "lab.other"})
        self.assertEqual(set(found[0]), {"id", "name", "login"})

    def test_finding_people_needs_two_characters_and_finds_at_most_ten(self):
        for number in range(12):
            self.create_user(f"lab.many{number:02}", LABORATORY_FILES_GROUP)

        self.assertApiRefused(INVALID_REQUEST, self.candidates("l"))
        self.assertApiRefused(
            INVALID_REQUEST, self.api("GET", f"/folders/{self.folder.id}/member-candidates", key=self.key)
        )
        self.assertEqual(len(self.candidates("lab.many").json()["candidates"]), 10)

    def test_only_who_may_share_the_folder_finds_people(self):
        self.assertApiRefused(PERMISSION_DENIED, self.candidates("lab.", self.members_key))
