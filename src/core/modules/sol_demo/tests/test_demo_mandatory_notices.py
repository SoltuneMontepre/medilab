from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_demo.demo_mandatory_notices import seed_mandatory_notices
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_NOTIFICATION


@tagged("post_install", "-at_install")
class TestDemoMandatoryNotices(TransactionCase):
    def portal_of_registered(self):
        user = self.env.ref("sol_demo.demo_res_users_registered")
        notifications = self.env[MODEL_MAIL_NOTIFICATION].sudo()
        return user, notifications.search(notifications._portal_domain(user))

    def test_the_customer_with_a_bounced_address_has_two_notices_in_the_portal_and_one_opened(self):
        user, notices = self.portal_of_registered()

        self.assertTrue(user.partner_id.email_bounced)
        self.assertEqual(len(notices), 2)
        self.assertEqual(len(notices.filtered("portal_seen_at")), 1)

    def test_seeding_again_changes_nothing(self):
        _user, before = self.portal_of_registered()
        seen = before.filtered("portal_seen_at").portal_seen_at

        seed_mandatory_notices(self.env)

        _user, after = self.portal_of_registered()
        self.assertEqual(after, before)
        self.assertEqual(after.filtered("portal_seen_at").portal_seen_at, seen)

    def test_the_customer_waiting_for_an_email_retry_has_a_future_attempt(self):
        hoa = self.env.ref("sol_demo.demo_res_partner_hoa")
        message = self.env.ref("sol_demo.demo_mail_message_temporary_email_retry")
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == hoa)

        self.assertEqual(notification.email_retry_attempts, 1)
        self.assertTrue(notification.next_email_retry_at)
        self.assertEqual(notification.mail_mail_id.state, "exception")

    def test_the_corrected_address_waits_for_confirmation(self):
        tai = self.env.ref("sol_demo.demo_res_partner_tai")
        confirmation = self.env["mail.mail"].search(
            [("email_to", "=", tai.email), ("email_confirmation", "=", True)], limit=1
        )

        self.assertTrue(tai.email_bounced)
        self.assertTrue(tai.email_confirmation_token)
        self.assertTrue(confirmation)
