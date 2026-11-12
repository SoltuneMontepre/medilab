from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_MAIL_NOTIFICATION

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.36.0" / "post-migrate.py"
# load_script names the module, and so the script's logger, after its second argument.
MIGRATION_LOGGER = "post_migrate"


@tagged("post_install", "-at_install")
class TestNoticeMigration(TransactionCase):
    """Notifications delivered before the portal column existed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env["res.users"].create(
            {
                "name": "Hoa",
                "login": "notice.migration.portal",
                "group_ids": [(6, 0, cls.env.ref("base.group_portal").ids)],
            }
        )
        staff = cls.env["res.users"].create(
            {
                "name": "Staff",
                "login": "notice.migration.staff",
                "group_ids": [(6, 0, cls.env.ref("base.group_user").ids)],
            }
        )
        messages = (
            cls.env[MODEL_MAIL_MESSAGE]
            .sudo()
            .create([{"body": "Old", "message_type": "notification"} for _ in range(2)])
        )
        notifications = cls.env[MODEL_MAIL_NOTIFICATION].sudo()
        cls.portal_inbox = notifications.create(
            {"mail_message_id": messages[0].id, "res_partner_id": portal.partner_id.id, "notification_type": "inbox"}
        )
        cls.portal_email = notifications.create(
            {"mail_message_id": messages[1].id, "res_partner_id": portal.partner_id.id, "notification_type": "email"}
        )
        cls.staff_inbox = notifications.create(
            {"mail_message_id": messages[0].id, "res_partner_id": staff.partner_id.id, "notification_type": "inbox"}
        )
        cls.all = cls.portal_inbox | cls.portal_email | cls.staff_inbox
        cls.before = {item.id: (item.notification_type, item.notification_status, item.is_read) for item in cls.all}

    def migrate(self):
        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.35.0")
        self.env.invalidate_all()

    def test_a_notice_in_a_portal_inbox_keeps_showing_in_the_portal(self):
        self.assertFalse(self.portal_inbox.portal_visible)
        self.migrate()
        self.assertTrue(self.portal_inbox.portal_visible)

    def test_other_notifications_are_not_shown_in_the_portal(self):
        self.migrate()
        self.assertFalse(self.portal_email.portal_visible)
        self.assertFalse(self.staff_inbox.portal_visible)

    def test_no_notification_is_lost_or_changed_and_nothing_is_marked_seen(self):
        self.migrate()
        self.assertTrue(self.all.exists() == self.all)
        for item in self.all:
            self.assertEqual((item.notification_type, item.notification_status, item.is_read), self.before[item.id])
            self.assertFalse(item.portal_seen_at)

    def test_running_it_twice_changes_nothing_more(self):
        self.migrate()
        self.migrate()
        self.assertTrue(self.portal_inbox.portal_visible)
        self.assertFalse(self.portal_email.portal_visible)
