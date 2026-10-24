from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    OWNER_ROLE,
    PERMISSION_DENIED,
    RAW_DATA,
    RESULT,
    UPLOAD_ONLY,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_LABORATORY_FOLDER,
    MODEL_PERSON,
    MODEL_SAMPLE,
)


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolders(LaboratoryFilesCase, RequestCase):
    """The head of the department that tests the lead sample creates its folders."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head = cls.create_head("hoa.head", "sample_read_all", "laboratory_folder_create_all")
        cls.department.manager_id = cls.head.employee_id

    @classmethod
    def create_head(cls, login, *permissions):
        person = cls.env[MODEL_PERSON].create(
            {
                "name": "Le Thi Hoa",
                "login": login,
                "department_id": cls.department.id,
                "permission_ids": [
                    Command.set([cls.env.ref(f"sol_laboratory.permission_{code}").id for code in permissions])
                ],
            }
        )
        return person.user_id

    def folders_of(self, sample):
        return self.env[MODEL_LABORATORY_FOLDER].search([("sample_id", "=", sample.id)])

    def test_the_head_creates_the_raw_data_and_result_folders_owned_by_them(self):
        action = self.sample.with_user(self.head).action_create_laboratory_folders()

        folders = self.folders_of(self.sample)
        self.assertEqual(sorted(folders.mapped("category")), sorted([RAW_DATA, RESULT]))
        self.assertEqual(folders.owner_id, self.head)
        self.assertEqual(set(folders.mapped("sync_mode")), {UPLOAD_ONLY})
        self.assertFalse(folders.rule_ids)
        self.assertEqual(folders.member_ids.filtered(lambda member: member.role == OWNER_ROLE).user_id, self.head)
        self.assertEqual(self.env[MODEL_LABORATORY_FOLDER].search(action["domain"]), folders)
        self.assertFalse(self.sample.laboratory_folders_missing)

    def test_the_folders_are_named_after_the_lab_code_only(self):
        self.sample.with_user(self.head).action_create_laboratory_folders()

        for folder in self.folders_of(self.sample):
            with self.subTest(category=folder.category):
                self.assertTrue(folder.name.startswith(self.sample.code))
                self.assertEqual(folder.root, f"{self.sample.code}-{folder.category}")
                self.assertNotIn(self.sample.customer_sample_name, folder.name)

    def test_creating_the_folders_twice_adds_no_second_folder_of_a_category(self):
        self.sample.with_user(self.head).action_create_laboratory_folders()
        folders = self.folders_of(self.sample)

        self.sample.with_user(self.head).action_create_laboratory_folders()

        self.assertEqual(self.folders_of(self.sample), folders)

    def test_only_the_missing_folder_is_added(self):
        raw_data = self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Raw data", "owner_id": self.tester.id, "sample_id": self.sample.id, "category": RAW_DATA}
        )
        self.assertTrue(self.sample.laboratory_folders_missing)

        self.sample.with_user(self.head).action_create_laboratory_folders()

        added = self.folders_of(self.sample) - raw_data
        self.assertEqual(added.category, RESULT)
        self.assertEqual(added.owner_id, self.head)
        self.assertEqual(raw_data.owner_id, self.tester)

    def test_only_the_head_of_a_department_that_tests_the_sample_creates_its_folders(self):
        other_head = self.create_head("lan.head", "sample_read_all", "laboratory_folder_create_all")
        self.env[MODEL_DEPARTMENT].create({"name": "Microbiology", "manager_id": other_head.employee_id.id})

        for user in (other_head, self.administrator):
            with self.subTest(user=user.login):
                self.assertRefused(PERMISSION_DENIED, self.sample.with_user(user).action_create_laboratory_folders)
        self.assertFalse(self.folders_of(self.sample))

    def test_the_head_needs_the_laboratory_files_permission_and_the_sample(self):
        without_files = self.create_head("minh.head", "sample_read_all")
        self.department.manager_id = without_files.employee_id
        self.assertRefused(PERMISSION_DENIED, self.sample.with_user(without_files).action_create_laboratory_folders)

        without_sample = self.create_head("tuan.head", "laboratory_folder_create_all")
        self.department.manager_id = without_sample.employee_id
        with self.assertRaises(AccessError):
            self.sample.with_user(without_sample).action_create_laboratory_folders()
        self.assertFalse(self.folders_of(self.sample))

    def test_a_folder_of_the_same_name_of_the_head_is_refused(self):
        self.env[MODEL_LABORATORY_FOLDER].create({"name": f"{self.sample.code}-raw", "owner_id": self.head.id})

        with self.assertRaises(UserError):
            self.sample.with_user(self.head).action_create_laboratory_folders()
        self.assertFalse(self.folders_of(self.sample))

    def test_the_sample_form_offers_the_folders_to_people_with_the_laboratory_files_permission(self):
        arch = self.env[MODEL_SAMPLE].with_user(self.head).get_views([(False, "form")])["views"]["form"]["arch"]

        self.assertIn('name="action_create_laboratory_folders"', arch)
        self.assertIn('name="action_open_laboratory_folders"', arch)
