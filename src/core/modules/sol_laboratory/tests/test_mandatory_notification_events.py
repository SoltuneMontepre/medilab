from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_MAIL_MESSAGE_SUBTYPE


@tagged("post_install", "-at_install")
class TestMandatoryNotificationEvents(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = new_test_user(
            cls.env,
            login="wf03.notification.administrator",
            groups="base.group_user,sol_laboratory.group_role_administrator",
        )
        cls.event = cls.env.ref("sol_laboratory.event_test_result_rejected")
        cls.optional = cls.env.ref("sol_laboratory.event_task_reminder")

    def assert_refused_unchanged(self, values):
        snapshot_fields = ["code", "mandatory", "enabled", "res_model", "write_date"]
        before = self.event.read(snapshot_fields)
        with self.assertRaisesRegex(UserError, "A mandatory event cannot be turned off"), self.env.cr.savepoint():
            self.event.with_user(self.administrator).write(values)
        self.assertEqual(self.event.read(snapshot_fields), before)
        self.assertEqual(self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(before[0]["code"]), self.event)

    def test_false_boolean_aliases_cannot_disable_a_mandatory_event(self):
        for inactive in (False, 0, None):
            with self.subTest(inactive=repr(inactive)):
                self.assert_refused_unchanged({"enabled": inactive})

    def test_false_boolean_aliases_cannot_make_a_mandatory_event_optional(self):
        for inactive in (False, 0, None):
            with self.subTest(inactive=repr(inactive)):
                self.assert_refused_unchanged({"mandatory": inactive})

    def test_a_mandatory_event_cannot_change_its_code(self):
        self.assert_refused_unchanged({"code": "test_result.rejected.renamed"})

    def test_a_mandatory_event_cannot_be_deleted(self):
        before = self.event.read(["code", "mandatory", "enabled", "write_date"])
        with self.assertRaisesRegex(UserError, "A mandatory event cannot be turned off"), self.env.cr.savepoint():
            self.event.with_user(self.administrator).unlink()
        self.assertTrue(self.event.exists())
        self.assertEqual(self.event.read(["code", "mandatory", "enabled", "write_date"]), before)
        self.assertEqual(self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(before[0]["code"]), self.event)

    def test_the_mandatory_event_code_and_classification_are_read_only_on_screen(self):
        arch = (
            self.env[MODEL_MAIL_MESSAGE_SUBTYPE]
            .with_user(self.administrator)
            .get_view(self.env.ref("sol_laboratory.view_medilab_notification_event_form").id)["arch"]
        )
        root = etree.fromstring(arch)
        for name in ("code", "mandatory", "enabled"):
            with self.subTest(field=name):
                fields = root.findall(f".//field[@name='{name}']")
                self.assertEqual(len(fields), 1)
                self.assertEqual(fields[0].get("readonly"), "mandatory")

    def test_an_optional_event_can_be_disabled_and_enabled_again(self):
        event = self.optional.with_user(self.administrator)
        code = event.code
        event.write({"enabled": False})
        self.assertFalse(self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(code))
        event.write({"enabled": True})
        self.assertEqual(self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(code), self.optional)

    def test_optional_event_metadata_remains_editable(self):
        event = self.optional.with_user(self.administrator)
        event.write({"code": "task.reminder.renamed", "mandatory": False, "description": "A different reminder"})
        self.assertEqual(event.code, "task.reminder.renamed")
        self.assertFalse(event.mandatory)
        event.write({"enabled": False})
        self.assertFalse(self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(event.code))

    def test_a_mandatory_event_still_allows_template_and_idempotent_metadata_edits(self):
        event = self.event.with_user(self.administrator)
        event.write(
            {"code": event.code, "mandatory": True, "enabled": True, "description": "A different rejection notice"}
        )
        self.assertEqual(event.description, "A different rejection notice")
        self.assertTrue(event.enabled)
        self.assertTrue(event.mandatory)

    def test_a_mixed_batch_cannot_partially_disable_optional_events(self):
        events = self.event | self.optional
        before = events.read(["mandatory", "enabled", "code", "write_date"])
        with self.assertRaisesRegex(UserError, "A mandatory event cannot be turned off"), self.env.cr.savepoint():
            events.with_user(self.administrator).write({"enabled": 0})
        self.assertEqual(events.read(["mandatory", "enabled", "code", "write_date"]), before)

    def test_system_migrations_can_reclassify_and_remove_an_event(self):
        self.event.write({"mandatory": False})
        self.event.unlink()
        self.assertFalse(self.event.exists())

    def test_a_refused_identity_change_leaves_the_mandatory_notice_deliverable(self):
        self.assert_refused_unchanged({"code": "test_result.rejected.renamed"})
        partner = self.administrator.partner_id
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            self.event.code,
            partner,
            "mandatory-notice-after-refusal",
            "A result was rejected",
            partners=partner,
        )
        self.assertTrue(message)
        self.assertEqual(message.subtype_id, self.event)
        notices = message.notification_ids.filtered(lambda notice: notice.res_partner_id == partner)
        self.assertEqual(len(notices), 1)
