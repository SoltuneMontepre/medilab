from freezegun import freeze_time

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_NOTIFICATION_PREFERENCE,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    CHANNEL_EMAIL,
    CHANNEL_POPUP,
    EVENT_TASK_REMINDER,
    EVENT_TEST_REPORT_ISSUED,
)

FIRST_OPEN = "2026-03-01 08:00:00"
LATER_OPEN = "2026-03-05 17:30:00"


@tagged("post_install", "-at_install")
class TestNoticeVisibility(TransactionCase):
    """A mandatory notice stays in the portal of the contact it was sent to, whatever its email does. Seen is the
    recipient's own, and the notification's channel, status and read flag keep the meaning Odoo gives them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref("base.group_portal")
        cls.business = cls.env["res.partner"].create({"name": "An Phu", "is_company": True})
        cls.hoa = cls.portal_contact("Hoa", "hoa@example.com", cls.business, portal)
        cls.khoa = cls.portal_contact("Khoa", "khoa@example.com", cls.business, portal)
        cls.binh = cls.portal_contact(
            "Binh", "binh@example.com", cls.env["res.partner"].create({"name": "Green"}), portal
        )
        cls.staff = cls.env["res.users"].create(
            {
                "name": "Staff",
                "login": "notice.staff",
                "email": "notice.staff@example.com",
                "notification_type": "inbox",
                "group_ids": [(6, 0, cls.env.ref("base.group_user").ids)],
            }
        )
        subtype = cls.env[MODEL_MAIL_MESSAGE_SUBTYPE]
        cls.mandatory = subtype._event(EVENT_TEST_REPORT_ISSUED)
        cls.optional = subtype._event(EVENT_TASK_REMINDER)
        department = cls.env["hr.department"].create({"name": "Notices"})
        cls.document = cls.env["medilab.task"].create(
            {
                "type_id": cls.env["medilab.task.type"].search([], limit=1).id,
                "name": "Notice",
                "department_id": department.id,
            }
        )
        cls.keys = 0

    @classmethod
    def portal_contact(cls, name, email, parent, group):
        user = cls.env["res.users"].create(
            {
                "name": name,
                "login": f"notice.{name.lower()}",
                "email": email,
                "group_ids": [(6, 0, group.ids)],
            }
        )
        user.partner_id.write({"parent_id": parent.id, "email": email})
        return user

    def raise_notice(self, partner, event=None):
        self.keys += 1
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            (event or self.mandatory).code, self.document, f"notice-{self.keys}", "Body", partners=partner
        )
        return message.notification_ids.filtered(lambda item: item.res_partner_id == partner)

    def listed_for(self, user):
        notifications = self.env[MODEL_MAIL_NOTIFICATION].sudo()
        return notifications.search(notifications._portal_domain(user))

    def test_a_mandatory_notice_is_visible_to_its_recipient_with_a_working_email(self):
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertTrue(notice.portal_visible)
        self.assertTrue(notice.mail_mail_id)
        self.assertIn(notice, self.listed_for(self.hoa))

    def test_a_mandatory_notice_stays_visible_when_the_email_bounced(self):
        self.hoa.partner_id.email_bounced = True
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertTrue(notice.portal_visible)
        self.assertFalse(notice.mail_mail_id)
        self.assertIn(notice, self.listed_for(self.hoa))

    def test_a_mandatory_notice_stays_visible_when_the_contact_has_no_email(self):
        self.hoa.partner_id.email = False
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertTrue(notice.portal_visible)
        self.assertFalse(notice.mail_mail_id)
        self.assertIn(notice, self.listed_for(self.hoa))

    def test_a_mandatory_notice_stays_visible_when_the_customer_switched_email_off(self):
        self.env[MODEL_NOTIFICATION_PREFERENCE].sudo().create(
            {"user_id": self.hoa.id, "event_id": self.mandatory.id, "channel": CHANNEL_EMAIL, "enabled": False}
        )
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertTrue(notice.portal_visible)
        self.assertIn(notice, self.listed_for(self.hoa))

    def test_an_email_that_will_not_be_sent_leaves_a_notice_the_inbox_does_not_wait_on(self):
        self.hoa.partner_id.email_bounced = True
        notice = self.raise_notice(self.hoa.partner_id)
        # Odoo reads the channel and the status: the notice is not an inbox item and no email is waiting.
        self.assertEqual(notice.notification_type, "email")
        self.assertEqual(notice.notification_status, "canceled")
        self.assertFalse(notice.is_read)

    def test_a_notice_with_a_queued_email_still_waits_for_it(self):
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertEqual(notice.notification_type, "email")
        self.assertEqual(notice.notification_status, "ready")

    def test_a_notice_that_is_not_mandatory_is_not_in_the_portal_unless_the_customer_chose_it(self):
        notice = self.raise_notice(self.hoa.partner_id, self.optional)
        self.assertFalse(notice.portal_visible)
        self.assertEqual(notice.notification_type, "email")
        self.assertNotIn(notice, self.listed_for(self.hoa))

    def test_a_customer_who_chose_the_portal_sees_a_notice_that_is_not_mandatory(self):
        self.env[MODEL_NOTIFICATION_PREFERENCE].sudo().create(
            {"user_id": self.hoa.id, "event_id": self.optional.id, "channel": CHANNEL_POPUP, "enabled": True}
        )
        notice = self.raise_notice(self.hoa.partner_id, self.optional)
        self.assertTrue(notice.portal_visible)
        self.assertEqual(notice.notification_type, "inbox")
        self.assertIn(notice, self.listed_for(self.hoa))

    def test_staff_keep_odoos_inbox_and_get_no_portal_notice(self):
        notice = self.raise_notice(self.staff.partner_id)
        self.assertFalse(notice.portal_visible)
        self.assertEqual(notice.notification_type, "inbox")
        self.assertEqual(notice.notification_status, "sent")
        # The inbox row of an internal user is listed as before, to that user only.
        self.assertIn(notice, self.listed_for(self.staff))
        self.assertNotIn(notice, self.listed_for(self.hoa))

    def test_a_contact_without_a_portal_account_has_nobody_who_can_open_the_notice(self):
        contact = self.env["res.partner"].create(
            {"name": "No Login", "parent_id": self.business.id, "email": "nologin@example.com"}
        )
        notice = self.raise_notice(contact)
        # Its email is queued, but nobody can open the notice in the portal: recipient-only visibility.
        self.assertFalse(notice.portal_visible)
        for user in (self.hoa, self.khoa):
            self.assertNotIn(notice, self.listed_for(user))

    def test_a_mandatory_notice_that_reaches_nobody_is_recorded(self):
        contact = self.env["res.partner"].create({"name": "Unreachable", "parent_id": self.business.id})
        entries = self.env[MODEL_AUDIT_ENTRY].search([("note", "like", "Notice not delivered")])
        notice = self.raise_notice(contact)
        self.assertFalse(notice)
        added = self.env[MODEL_AUDIT_ENTRY].search([("note", "like", "Notice not delivered")]) - entries
        self.assertEqual(len(added), 1)
        self.assertEqual(added.action, "error")
        self.assertNotIn("@", added.note or "")

    def test_a_notice_that_is_not_mandatory_reaching_nobody_is_not_recorded(self):
        contact = self.env["res.partner"].create({"name": "Unreachable", "parent_id": self.business.id})
        entries = self.env[MODEL_AUDIT_ENTRY].search([("note", "like", "Notice not delivered")])
        self.raise_notice(contact, self.optional)
        self.assertEqual(self.env[MODEL_AUDIT_ENTRY].search([("note", "like", "Notice not delivered")]), entries)

    def test_each_contact_sees_only_the_notices_addressed_to_it(self):
        mine = self.raise_notice(self.hoa.partner_id)
        colleague = self.raise_notice(self.khoa.partner_id)
        other_business = self.raise_notice(self.binh.partner_id)
        self.assertEqual(self.listed_for(self.hoa), mine)
        self.assertEqual(self.listed_for(self.khoa), colleague)
        self.assertEqual(self.listed_for(self.binh), other_business)

    def test_the_first_open_is_recorded_once_and_a_later_open_keeps_it(self):
        notice = self.raise_notice(self.hoa.partner_id)
        self.assertFalse(notice.portal_seen_at)
        with freeze_time(FIRST_OPEN):
            notice._portal_open()
        first = notice.portal_seen_at
        self.assertEqual(str(first), FIRST_OPEN)
        with freeze_time(LATER_OPEN):
            notice._portal_open()
        self.assertEqual(notice.portal_seen_at, first)

    def test_seen_belongs_to_the_recipient_that_opened_it(self):
        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_TEST_REPORT_ISSUED,
            self.document,
            "shared-notice",
            "Body",
            partners=self.hoa.partner_id | self.khoa.partner_id,
        )
        hoa_row = message.notification_ids.filtered(lambda item: item.res_partner_id == self.hoa.partner_id)
        khoa_row = message.notification_ids.filtered(lambda item: item.res_partner_id == self.khoa.partner_id)
        hoa_row._portal_open()
        self.assertTrue(hoa_row.portal_seen_at)
        self.assertFalse(khoa_row.portal_seen_at)

    def test_opening_a_notice_leaves_odoos_read_flag_and_the_document_alone(self):
        notice = self.raise_notice(self.hoa.partner_id)
        status, written = self.document.status, self.document.write_date
        notice._portal_open()
        self.assertFalse(notice.is_read)
        self.assertFalse(notice.read_date)
        self.assertEqual(self.document.status, status)
        self.assertEqual(self.document.write_date, written)

    def test_the_notice_does_not_change_the_document_it_is_about(self):
        status, written = self.document.status, self.document.write_date
        self.raise_notice(self.hoa.partner_id)
        self.assertEqual(self.document.status, status)
        self.assertEqual(self.document.write_date, written)
