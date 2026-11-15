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
