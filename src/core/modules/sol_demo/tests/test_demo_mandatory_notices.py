from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_demo.demo_mandatory_notices import seed_mandatory_notices
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_NOTIFICATION


@tagged("post_install", "-at_install")
class TestDemoMandatoryNotices(TransactionCase):
    def portal_of_registered(self):
        user = self.env.ref("sol_demo.demo_res_users_registered")
        notifications = self.env[MODEL_MAIL_NOTIFICATION].sudo()
        return user, notifications.search(notifications._portal_domain(user))

    def test_the_registered_customer_sees_bounced_and_correction_notices(self):
        user, notices = self.portal_of_registered()

        self.assertTrue(user.partner_id.email_bounced)
        self.assertEqual(len(notices), 3)
        self.assertEqual(len(notices.filtered("portal_seen_at")), 1)
        self.assertTrue(user.partner_id.email_confirmation_token_hash)
        self.assertTrue(user.partner_id.email_confirmation_expires_at)
        self.assertFalse(
            notices.filtered(
                lambda item: item.mail_message_id.notification_key == "demo:email_correction_waiting"
            ).mail_mail_id
        )

    def test_a_temporary_delivery_failure_waits_for_retry_in_the_customer_portal(self):
        user = self.env.ref("sol_demo.demo_res_users_customer")
        notices = (
            self.env[MODEL_MAIL_NOTIFICATION].sudo().search(self.env[MODEL_MAIL_NOTIFICATION]._portal_domain(user))
        )

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices.brevo_status, "deferred")
        self.assertEqual(notices.notification_status, "exception")
        self.assertEqual(notices.email_retry_count, 1)

    def test_seeding_again_changes_nothing(self):
        _user, before = self.portal_of_registered()
        seen = before.filtered("portal_seen_at").portal_seen_at

        seed_mandatory_notices(self.env)

        _user, after = self.portal_of_registered()
        self.assertEqual(after, before)
        self.assertEqual(after.filtered("portal_seen_at").portal_seen_at, seen)
