from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_sample_folder_case import LaboratorySampleFolderCase
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST, MEMBER_ROLE, NOT_FOUND, RESULT


@tagged("post_install", "-at_install")
class TestLaboratoryApiSampleFolders(LaboratoryApiCase, LaboratorySampleFolderCase):
    """A folder of a sample through the laboratory files API, for members who see its sample and one who does not."""

    def setUp(self):
        super().setUp()
        self.results = self.folder_of_category(
            RESULT, name="Results", member_ids=[Command.create({"user_id": self.outsider.id, "role": MEMBER_ROLE})]
        )
        self.key = self.signed_in_key(self.tester, "tester-installation")
        self.outsiders_key = self.signed_in_key(self.outsider, "outsiders-installation")

    def test_a_member_who_sees_the_sample_gets_its_folder_with_the_sample(self):
        folder = self.api("GET", f"/folders/{self.results.id}", key=self.key).json()["folder"]

        sample = self.results.sample_id
        self.assertEqual((folder["category"], folder["sample"]), (RESULT, {"id": sample.id, "lab_code": sample.code}))

    def test_a_member_who_does_not_see_the_sample_gets_nothing_of_its_folder(self):
        listed = [folder["id"] for folder in self.api("GET", "/folders", key=self.outsiders_key).json()["folders"]]

        self.assertNotIn(self.results.id, listed)
        for path in (
            f"/folders/{self.results.id}",
            f"/folders/{self.results.id}/members",
            f"/folders/{self.results.id}/rules",
        ):
            with self.subTest(path=path):
                self.assertApiRefused(NOT_FOUND, self.api("GET", path, key=self.outsiders_key))

    def test_a_folder_created_through_the_api_has_no_sample_and_no_category(self):
        sample = self.results.sample_id.id
        for extra in ({"category": RESULT}, {"sample_id": sample}):
            with self.subTest(extra=extra):
                created = self.api("POST", "/folders", {"name": "Mine", **extra}, key=self.key)
                self.assertApiRefused(INVALID_REQUEST, created)
