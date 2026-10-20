from odoo.tests import Form, tagged

from .laboratory_signing_case import LaboratorySigningCase
from odoo.addons.sol_laboratory.constants.approvals import STATE_APPROVED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFileSigningBackOffice(LaboratorySigningCase):
    def arch(self, model, user, view_type="form"):
        return self.env[model].with_user(user).get_views([(False, view_type)])["views"][view_type]["arch"]

    def test_the_version_form_signs_rejects_and_withdraws(self):
        arch = self.arch(MODEL_LABORATORY_FILE_VERSION, self.head.user_id)

        for name in ("action_sign", "action_withdraw", "approval_state", "signature_ids"):
            with self.subTest(name=name):
                self.assertIn(f'name="{name}"', arch)
        self.assertIn(str(self.env.ref("sol_laboratory.action_medilab_laboratory_file_version_reject").id), arch)

    def test_only_people_who_read_signatures_see_them_on_the_version(self):
        arch = self.arch(MODEL_LABORATORY_FILE_VERSION, self.saver.user_id)

        self.assertNotIn('name="signature_ids"', arch)
        self.assertIn('name="approval_state"', arch)

    def test_the_head_sees_the_signatures_of_a_signed_version(self):
        version = self.result_version()
        self.as_person(version, self.head).action_sign()

        form = Form(version.with_user(self.head.user_id))

        self.assertEqual(form.approval_state, STATE_APPROVED)
        self.assertEqual(len(form.signature_ids), 1)
        self.assertEqual(version.with_user(self.head.user_id).signature_ids.signer_name, self.head.name)

    def test_files_show_whether_their_current_version_is_signed(self):
        for view_type in ("list", "form"):
            with self.subTest(view_type=view_type):
                self.assertIn(
                    'name="current_approval_state"', self.arch(MODEL_LABORATORY_FILE, self.saver.user_id, view_type)
                )

    def test_a_folder_that_holds_files_shows_its_sample_and_category_read_only(self):
        arch = self.arch(MODEL_LABORATORY_FOLDER, self.env.ref("base.user_admin"))

        for name in ("sample_id", "category"):
            with self.subTest(name=name):
                self.assertRegex(arch, rf'name="{name}"[^>]*readonly="file_ids"')
