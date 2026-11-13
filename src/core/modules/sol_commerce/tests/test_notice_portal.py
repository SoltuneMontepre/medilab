import re
from datetime import datetime, timedelta

from odoo.tests import HttpCase, tagged

from odoo.addons.sol_commerce.constants.notifications import EVENT_INVOICE_SENT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
)
from odoo.addons.sol_laboratory.constants.settings import NOTICE_PORTAL_SINCE_PARAMETER

LISTED = re.compile(r'id="notification-\d+')
OLD_OPEN = "2026-01-01 00:00:00"
PER_PAGE = 20
CUTOVER = datetime(2026, 3, 1, 8, 0, 0)


@tagged("post_install", "-at_install")
class TestNoticePortal(HttpCase):
    """What a signed-in customer reads of a mandatory notice, and what another customer or contact cannot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref("base.group_portal")
        cls.business = cls.env["res.partner"].create({"name": "An Phu", "is_company": True, "vat": "0312345678"})
        cls.hoa = cls.portal_contact("Hoa", cls.business, portal)
        cls.khoa = cls.portal_contact("Khoa", cls.business, portal)
        cls.binh = cls.portal_contact("Binh", cls.env["res.partner"].create({"name": "Green Farm"}), portal)
        cls.keys = 0

    @classmethod
    def portal_contact(cls, name, parent, group):
        login = f"{name.lower()}.notice"
        user = cls.env["res.users"].create(
            {"name": name, "login": login, "password": login, "group_ids": [(6, 0, group.ids)]}
        )
        user.partner_id.write({"parent_id": parent.id, "email": f"{login}@example.com"})
        return user

    def raise_notice(self, user, subject="Invoice HD-1", body="Invoice HD-1 is attached."):
        self.keys += 1
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_INVOICE_SENT,
            self.business,
            f"portal-notice-{self.keys}",
            body,
            subject=subject,
            partners=user.partner_id,
        )
        return message.notification_ids.filtered(lambda item: item.res_partner_id == user.partner_id)

    def old_code_notice(self, user, written, subject="Invoice HD-2"):
        """A notice written by code that does not know the portal columns, in a message created at `written`."""
        notice = self.raise_notice(user, subject=subject)
        self.env.cr.execute("UPDATE mail_notification SET portal_visible = NULL WHERE id = %s", (notice.id,))
        self.env.cr.execute(
            "UPDATE mail_message SET create_date = %s WHERE id = %s", (written, notice.mail_message_id.id)
        )
        self.env.invalidate_all()
        return notice

    def get(self, user, path, **kwargs):
        self.authenticate(user.login, user.login)
        return self.url_open(path, **kwargs)

    def test_a_bounced_notice_is_listed_and_new(self):
        self.hoa.partner_id.email_bounced = True
        notice = self.raise_notice(self.hoa)
        page = self.get(self.hoa, "/my/notifications")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'id="notification-{notice.id}"', page.text)
        self.assertIn(f"/my/notifications/{notice.id}", page.text)
        self.assertIn("Invoice HD-1", page.text)
        self.assertIn("New", page.text)
        # The list shows the title and date; the text is read on the notice.
        self.assertNotIn("is attached", page.text)

    def test_opening_a_notice_shows_it_and_records_the_first_open_once(self):
        notice = self.raise_notice(self.hoa)
        opened = self.get(self.hoa, f"/my/notifications/{notice.id}")
        self.assertEqual(opened.status_code, 200)
        self.assertIn("Invoice HD-1 is attached.", opened.text)
        self.env.invalidate_all()
        self.assertTrue(notice.portal_seen_at)
        notice.sudo().write({"portal_seen_at": OLD_OPEN})
        self.url_open(f"/my/notifications/{notice.id}")
        self.env.invalidate_all()
        self.assertEqual(str(notice.portal_seen_at), OLD_OPEN)

    def test_a_seen_notice_is_no_longer_marked_new_and_odoos_read_flag_is_untouched(self):
        notice = self.raise_notice(self.hoa)
        self.get(self.hoa, f"/my/notifications/{notice.id}")
        page = self.url_open("/my/notifications")
        self.assertNotIn("badge text-bg-primary", page.text)
        self.env.invalidate_all()
        self.assertFalse(notice.is_read)

    def test_another_contact_of_the_business_cannot_read_the_notice(self):
        notice = self.raise_notice(self.hoa)
        listed = self.get(self.khoa, "/my/notifications")
        self.assertNotIn(f"notification-{notice.id}", listed.text)
        denied = self.url_open(f"/my/notifications/{notice.id}")
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn("Invoice HD-1 is attached.", denied.text)
        self.env.invalidate_all()
        self.assertFalse(notice.portal_seen_at)

    def test_another_customer_cannot_read_the_notice(self):
        notice = self.raise_notice(self.hoa)
        listed = self.get(self.binh, "/my/notifications")
        self.assertNotIn(f"notification-{notice.id}", listed.text)
        denied = self.url_open(f"/my/notifications/{notice.id}")
        self.assertEqual(denied.status_code, 404)
        self.env.invalidate_all()
        self.assertFalse(notice.portal_seen_at)

    def test_a_notice_that_is_not_shown_in_the_portal_is_not_found(self):
        message = self.env[MODEL_MAIL_MESSAGE].sudo().create({"body": "Hidden", "message_type": "notification"})
        hidden = (
            self.env[MODEL_MAIL_NOTIFICATION]
            .sudo()
            .create(
                {"mail_message_id": message.id, "res_partner_id": self.hoa.partner_id.id, "notification_type": "email"}
            )
        )
        response = self.get(self.hoa, f"/my/notifications/{hidden.id}")
        self.assertEqual(response.status_code, 404)

    def test_a_missing_notice_is_not_found(self):
        self.assertEqual(self.get(self.hoa, "/my/notifications/999999999").status_code, 404)

    def test_a_visitor_is_sent_to_sign_in(self):
        notice = self.raise_notice(self.hoa)
        self.authenticate(None, None)
        response = self.url_open(f"/my/notifications/{notice.id}", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("login", response.headers["Location"])

    def test_the_list_pages_so_no_notice_drops_out(self):
        notices = [self.raise_notice(self.hoa, subject=f"Notice {number}") for number in range(PER_PAGE + 1)]
        first = self.get(self.hoa, "/my/notifications")
        self.assertEqual(len(LISTED.findall(first.text)), PER_PAGE)
        self.assertIn("/my/notifications/page/2", first.text)
        second = self.url_open("/my/notifications/page/2")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(LISTED.findall(second.text)), 1)
        self.assertIn(f'id="notification-{notices[0].id}"', second.text)

    def test_the_preferences_page_still_lists_the_events(self):
        page = self.get(self.hoa, "/my/notifications")
        self.assertIn("event-invoice.sent", page.text)
        self.assertIn("notification-preferences", page.text)
        self.assertIn("No notifications yet.", page.text)

    def test_a_notice_old_code_wrote_after_the_cutover_is_read_by_its_recipient_only(self):
        self.env[MODEL_IR_CONFIG_PARAMETER].sudo().set_str(NOTICE_PORTAL_SINCE_PARAMETER, str(CUTOVER))
        notice = self.old_code_notice(self.hoa, CUTOVER + timedelta(seconds=1))
        listed = self.get(self.hoa, "/my/notifications")
        self.assertIn(f'id="notification-{notice.id}"', listed.text)
        self.assertEqual(self.url_open(f"/my/notifications/{notice.id}").status_code, 200)
        for other in (self.khoa, self.binh):
            self.assertNotIn(f"notification-{notice.id}", self.get(other, "/my/notifications").text)
            self.assertEqual(self.url_open(f"/my/notifications/{notice.id}").status_code, 404)

    def test_a_notice_written_before_the_cutover_or_with_no_cutover_is_not_found(self):
        notice = self.old_code_notice(self.hoa, CUTOVER - timedelta(seconds=1))
        parameters = self.env[MODEL_IR_CONFIG_PARAMETER].sudo()
        parameters.set_str(NOTICE_PORTAL_SINCE_PARAMETER, str(CUTOVER))
        self.assertEqual(self.get(self.hoa, f"/my/notifications/{notice.id}").status_code, 404)
        parameters.search([("key", "=", NOTICE_PORTAL_SINCE_PARAMETER)]).unlink()
        newer = self.old_code_notice(self.hoa, CUTOVER + timedelta(days=1))
        self.assertEqual(self.url_open(f"/my/notifications/{newer.id}").status_code, 404)
        self.assertNotIn(f"notification-{newer.id}", self.url_open("/my/notifications").text)

    def test_every_portal_account_of_a_contact_reads_its_notice(self):
        twin = self.env["res.users"].create(
            {
                "name": "Hoa Twin",
                "login": "hoa.twin.notice",
                "password": "hoa.twin.notice",
                "partner_id": self.hoa.partner_id.id,
                "group_ids": [(6, 0, self.env.ref("base.group_portal").ids)],
            }
        )
        notice = self.raise_notice(self.hoa)
        for user in (self.hoa, twin):
            self.assertEqual(self.get(user, f"/my/notifications/{notice.id}").status_code, 200)
        self.assertEqual(self.get(self.khoa, f"/my/notifications/{notice.id}").status_code, 404)
