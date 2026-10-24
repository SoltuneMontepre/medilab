from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_DIGITAL_SIGNATURE,
    MODEL_DOCUMENT_LOCK,
    MODEL_IR_ACCESS,
    MODEL_IR_ACTIONS_ACT_WINDOW_VIEW,
    MODEL_IR_ACTIONS_REPORT,
    MODEL_IR_MAIL_SERVER,
    MODEL_IR_UI_MENU,
    MODEL_IR_UI_VIEW,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_SIGN_IN_ATTEMPT,
    MODEL_MAIL_MAIL,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_PUSH_DELIVERY,
    MODEL_REGULATION,
    MODEL_RES_USERS,
    MODEL_SIGNATURE,
)

HISTORY_BUTTON = 'name="action_open_audit_history"'


@tagged("post_install", "-at_install")
class TestAuditAccess(AuditCase):
    def test_a_person_without_the_permission_cannot_see_the_trail_but_produces_entries(self):
        self.limit.with_user(self.editor).max_value = 0.02

        self.assertEqual(self.entries(self.limit, "edit").user_id, self.editor)
        with self.assertRaises(AccessError):
            self.env[MODEL_AUDIT_ENTRY].with_user(self.editor).search([])

    def test_an_auditor_reads_entries_and_their_changes(self):
        self.limit.max_value = 0.02

        entry = (
            self.env[MODEL_AUDIT_ENTRY]
            .with_user(self.auditor)
            .search(
                [
                    ("document_model", "=", self.limit._name),
                    ("document_id", "=", self.limit.id),
                    ("action", "=", "edit"),
                ]
            )
        )
        self.assertEqual(entry.change_ids.mapped("new_value"), ["0.02"])

    def test_only_auditors_see_the_history_button(self):
        regulations = self.env[MODEL_REGULATION]

        self.assertIn(HISTORY_BUTTON, regulations.with_user(self.auditor).get_view(view_type="form")["arch"])
        self.assertNotIn(HISTORY_BUTTON, regulations.with_user(self.editor).get_view(view_type="form")["arch"])

    def test_a_form_without_a_sheet_gets_the_history_button_below_its_header(self):
        arch = etree.fromstring("<form><header/><group/></form>")

        self.env[MODEL_REGULATION]._add_history_button(arch)

        self.assertEqual([child.tag for child in arch], ["header", "div", "group"])
        button = arch[1].find("button")
        if button is None:
            self.fail("The history button is missing.")
        self.assertEqual(button.get("name"), "action_open_audit_history")

    def test_every_document_model_of_the_laboratory_is_audited(self):
        # The trail itself, and the records the trail already describes: signatures, digital signatures, the work of
        # jobs, such as the pushes of a notification, the emails and notifications of messages, which integration
        # entries describe, document locks, whose release by an administrator is an entry on the document, and the
        # changes of laboratory files, each the new current version a version's own entry describes, and their stored
        # content, which the versions and uploads holding it describe. Failed sign-ins of laboratory files are counted,
        # not audited, as Odoo's log records them.
        # Users keep their personal data on their contact and get their access from their person's roles. Views,
        # menus and reports change when modules are installed, accesses follow from permissions, and the mail server
        # comes from the environment.
        unaudited = {
            MODEL_AUDIT_ENTRY,
            MODEL_AUDIT_CHANGE,
            MODEL_SIGNATURE,
            MODEL_DIGITAL_SIGNATURE,
            MODEL_DOCUMENT_LOCK,
            MODEL_LABORATORY_FILE_CHANGE,
            MODEL_LABORATORY_CONTENT,
            MODEL_LABORATORY_SIGN_IN_ATTEMPT,
            MODEL_JOB_ITEM,
            MODEL_JOB_RUN,
            MODEL_PUSH_DELIVERY,
            MODEL_MAIL_MESSAGE,
            MODEL_MAIL_NOTIFICATION,
            MODEL_MAIL_MAIL,
            MODEL_RES_USERS,
            MODEL_IR_UI_VIEW,
            MODEL_IR_UI_MENU,
            MODEL_IR_ACCESS,
            MODEL_IR_ACTIONS_ACT_WINDOW_VIEW,
            MODEL_IR_ACTIONS_REPORT,
            MODEL_IR_MAIL_SERVER,
        }

        self.assertEqual(self.unaudited_documents("sol_laboratory"), unaudited)
