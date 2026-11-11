from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, RESULT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import FOLDER_ADMINISTRATION_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"


@tagged("post_install", "-at_install")
class TestLaboratoryEditingSampleFolder(LaboratoryEditingCase, RequestCase):
    """A session on a results spreadsheet of the lead sample's results folder, which the second tester is a member of,
    next to a session on the HPLC folder's spreadsheet of no sample."""

    def setUp(self):
        super().setUp()
        self.folder_administrator = self.create_user(
            "lab.folders",
            FOLDER_ADMINISTRATION_GROUP,
            "sol_laboratory.group_permission_laboratory_editing_session_read_all",
        )
        results = self.env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": "Results",
                "owner_id": self.tester.id,
                "sample_id": self.sample.id,
                "category": RESULT,
                "member_ids": [Command.create({"user_id": self.member.id, "role": MEMBER_ROLE})],
            }
        )
        sample_file = self.file_of("Kết quả chì.xlsx", results)
        self.save(sample_file, "Chì, bản 1")
        self.of_sample = self.new_session(sample_file)
        self.of_no_sample = self.new_session()

    def visible(self, user):
        sessions = self.of_sample | self.of_no_sample
        return self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(user).search([("id", "in", sessions.ids)])

    def test_a_session_in_a_folder_of_the_sample_is_hidden_from_people_who_cannot_see_the_sample(self):
        for user in (self.member, self.folder_administrator):
            with self.subTest(user=user.login):
                self.assertEqual(self.visible(user), self.of_no_sample)
                with self.assertRaises(AccessError):
                    self.of_sample.with_user(user).read(["display_name"])

            user.group_ids = [Command.link(persisted_id(self.env.ref(SAMPLE_READER_GROUP)))]
            with self.subTest(user=user.login, sees_sample=True):
                self.assertEqual(self.visible(user), self.of_sample | self.of_no_sample)
