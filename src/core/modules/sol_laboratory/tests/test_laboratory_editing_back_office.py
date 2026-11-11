from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_UI_MENU,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
)


@tagged("post_install", "-at_install")
class TestLaboratoryEditingBackOffice(LaboratoryEditingCase):
    def test_editing_sessions_show_under_documents_to_people_with_the_laboratory_files_permission(self):
        menu = self.env.ref("sol_laboratory.menu_laboratory_editing_session").id

        for user in (self.tester, self.administrator):
            with self.subTest(user=user.login):
                self.assertIn(menu, self.env[MODEL_IR_UI_MENU].with_user(user)._visible_menu_ids())
        self.assertNotIn(menu, self.env[MODEL_IR_UI_MENU].with_user(self.colleague)._visible_menu_ids())

    def test_the_back_office_reads_editing_sessions_and_changes_nothing(self):
        session = self.new_session()
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION]

        for user in (self.member, self.administrator):
            with self.subTest(user=user.login):
                views = sessions.with_user(user).get_views([(False, "list"), (False, "form"), (False, "search")])
                self.assertEqual(set(views["views"]), {"list", "form", "search"})
                self.assertNotIn("callback_token", "".join(view["arch"] for view in views["views"].values()))
                with self.assertRaises(AccessError):
                    session.with_user(user).write({"last_activity_at": "2026-10-21 08:00:00"})
        self.assertEqual(session.with_user(self.member).opened_by_id, self.tester)

    def test_a_file_lists_its_editing_sessions(self):
        session = self.new_session()
        arch = self.env[MODEL_LABORATORY_FILE].with_user(self.member).get_views([(False, "form")])["views"]["form"]

        self.assertIn('name="editing_session_ids"', arch["arch"])
        self.assertEqual(self.file.with_user(self.member).editing_session_ids, session)
