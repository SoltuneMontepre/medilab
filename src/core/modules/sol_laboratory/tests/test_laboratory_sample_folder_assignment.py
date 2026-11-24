from freezegun import freeze_time

from odoo.tests import new_test_user, tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP

LABORATORY_FILES = "laboratory_folder.create.all"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderAssignment(SchedulingCase):
    """The person a testing task is assigned to gets the raw-data and result folders of its sample, created when the
    sample lacks them and owned by the head of the task's department."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for person in (cls.tester, cls.other_tester, cls.head):
            cls.grant(person, LABORATORY_FILES, "sample.read.all")
        cls.department.manager_id = cls.head.employee_id

    def folders_of(self, sample):
        return self.env[MODEL_LABORATORY_FOLDER].search([("sample_id", "=", sample.id)])

    def members_of(self, folder):
        return folder.member_ids.filtered(lambda member: member.role == MEMBER_ROLE).user_id

    def test_claiming_a_testing_task_gives_the_tester_the_folders_of_its_sample(self):
        task = self.testing_task(self.test)

        self.as_person(task, self.tester).action_claim()

        folders = self.folders_of(self.sample)
        self.assertEqual(sorted(folders.mapped("category")), sorted([RAW_DATA, RESULT]))
        self.assertEqual(folders.owner_id, self.head.user_id)
        for folder in folders:
            with self.subTest(category=folder.category):
                self.assertEqual(self.members_of(folder), self.tester.user_id)

    def test_an_assigned_tester_joins_the_folders_the_sample_already_has(self):
        folders = self.sample._create_laboratory_folders(self.other_tester.user_id)

        self.testing_task(self.test, self.tester)

        self.assertEqual(self.folders_of(self.sample), folders)
        self.assertEqual(folders.owner_id, self.other_tester.user_id)
        for folder in folders:
            with self.subTest(category=folder.category):
                self.assertEqual(self.members_of(folder), self.tester.user_id)

    def test_reassigning_adds_the_new_tester_and_keeps_the_earlier_one(self):
        task = self.testing_task(self.test, self.tester)

        task.write({"assignee_id": self.other_tester.id, "reassign_reason": "On leave"})

        folders = self.folders_of(self.sample)
        self.assertEqual(len(folders), 2)
        for folder in folders:
            with self.subTest(category=folder.category):
                self.assertEqual(self.members_of(folder), self.tester.user_id | self.other_tester.user_id)

    def test_a_tester_without_the_laboratory_files_permission_is_assigned_and_joins_no_folder(self):
        plain = self.create_person("Vo Thi Giang", self.department, "giang.vo", permissions=("sample_test.read.all",))

        task = self.testing_task(self.test, plain)

        self.assertEqual((task.assignee_id, task.status), (plain, "assigned"))
        folders = self.folders_of(self.sample)
        self.assertEqual(len(folders), 2)
        self.assertNotIn(plain.user_id, folders.member_ids.user_id)

    def test_a_department_whose_head_cannot_use_laboratory_files_gets_no_folder(self):
        self.department.manager_id = False

        task = self.testing_task(self.test, self.tester)

        self.assertEqual(task.status, "assigned")
        self.assertFalse(self.folders_of(self.sample))

    def test_a_folder_name_the_head_already_uses_does_not_stop_the_assignment(self):
        self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Own raw data", "root": f"{self.sample.code}-{RAW_DATA}", "owner_id": self.head.user_id.id}
        )

        task = self.testing_task(self.test, self.tester)

        self.assertEqual(task.status, "assigned")
        self.assertFalse(self.folders_of(self.sample))

    def test_an_archived_folder_takes_no_new_member(self):
        task = self.testing_task(self.test, self.tester)
        administrator = new_test_user(
            self.env, login="lab.administrator", groups=f"base.group_user,{ADMINISTRATOR_GROUP}"
        )
        for folder in self.folders_of(self.sample).with_user(administrator):
            folder.action_archive_folder()

        task.write({"assignee_id": self.other_tester.id, "reassign_reason": "On leave"})

        self.assertEqual(task.assignee_id, self.other_tester)
        folders = self.folders_of(self.sample)
        self.assertIn(self.tester.user_id, folders.member_ids.user_id)
        self.assertNotIn(self.other_tester.user_id, folders.member_ids.user_id)

    def test_a_testing_task_opens_the_files_of_its_sample(self):
        task = self.testing_task(self.test, self.tester)
        raw_data = self.folders_of(self.sample).filtered(lambda folder: folder.category == RAW_DATA)
        files = self.env[MODEL_LABORATORY_FILE]
        run = files._get_or_create(raw_data, "run-01.csv")
        elsewhere = self.env[MODEL_LABORATORY_FOLDER].create({"name": "HPLC", "owner_id": self.tester.user_id.id})
        files._get_or_create(elsewhere, "notes.txt")
        as_tester = self.as_person(task, self.tester)

        action = as_tester.action_open_laboratory_files()

        self.assertEqual(as_tester.laboratory_file_count, 1)
        self.assertEqual(files.with_user(self.tester.user_id).search(action["domain"]), run)

    def test_a_task_the_system_did_not_link_opens_no_files(self):
        task = self.testing_task(self.test, self.tester)
        files = self.env[MODEL_LABORATORY_FILE]
        files._get_or_create(self.folders_of(self.sample)[:1], "run-01.csv")
        elsewhere = self.env[MODEL_LABORATORY_FOLDER].create({"name": "HPLC", "owner_id": self.tester.user_id.id})
        files._get_or_create(elsewhere, "notes.txt")

        task.linked_by_system = False

        self.assertEqual(task.laboratory_file_count, 0)
        self.assertFalse(files.search(task.action_open_laboratory_files()["domain"]))
