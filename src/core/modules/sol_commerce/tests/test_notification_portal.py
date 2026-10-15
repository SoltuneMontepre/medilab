import re

from odoo.tests import HttpCase, tagged

from odoo.addons.sol_commerce.constants.notifications import (
    EVENT_INVOICE_SENT,
    EVENT_ORDER_UPDATED,
    EVENT_QUOTATION_SENT,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL


@tagged("post_install", "-at_install")
class TestNotificationPortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.business = cls.env["res.partner"].create({"name": "An Phu", "is_company": True, "vat": "0312345678"})
        cls.hoa = cls.env["res.partner"].create(
            {"name": "Hoa", "email": "hoa@example.com", "parent_id": cls.business.id, "type": "contact"}
        )
        cls.khoa = cls.env["res.partner"].create(
            {"name": "Khoa", "email": "khoa@example.com", "parent_id": cls.business.id, "type": "contact"}
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "Hoa",
                "login": "hoa.portal",
                "password": "hoa.portal",
                "partner_id": cls.hoa.id,
                "group_ids": [(6, 0, cls.env.ref("base.group_portal").ids)],
            }
        )
        subtype = cls.env["mail.message.subtype"]
        cls.quotation_sent = subtype._event(EVENT_QUOTATION_SENT)
        cls.order_updated = subtype._event(EVENT_ORDER_UPDATED)
        cls.invoice_sent = subtype._event(EVENT_INVOICE_SENT)

    def save(self, **fields):
        self.authenticate("hoa.portal", "hoa.portal")
        page = self.url_open("/my/notifications")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        return self.url_open("/my/notifications", data={"csrf_token": token, **fields})

    def test_the_page_lists_the_events_to_choose_from(self):
        self.authenticate("hoa.portal", "hoa.portal")
        page = self.url_open("/my/notifications")
        self.assertEqual(page.status_code, 200)
        self.assertIn("event-quotation.sent", page.text)
        self.assertIn("event-invoice.sent", page.text)

    def test_saving_turns_a_channel_off_for_the_next_notification(self):
        response = self.save(**{"order.updated:popup": "on"})
        self.assertTrue(response.url.endswith("saved=1"))
        channels = self.env["mail.message"]._channels_for(self.hoa, self.order_updated)
        self.assertNotIn(CHANNEL_EMAIL, channels)

    def test_saving_never_switches_a_mandatory_event_off(self):
        self.save()
        channels = self.env["mail.message"]._channels_for(self.hoa, self.invoice_sent)
        self.assertIn(CHANNEL_EMAIL, channels)
        preferences = self.env["medilab.notification.preference"].search(
            [("user_id", "=", self.user.id), ("event_id", "=", self.invoice_sent.id)]
        )
        self.assertFalse(preferences)

    def test_saving_a_contact_routes_the_event_to_it(self):
        self.save(**{"contact:quotation.sent": str(self.khoa.id), "quotation.sent:email": "on"})
        recipients = self.env["mail.message"]._event_partners(self.quotation_sent, self.hoa)
        self.assertEqual(recipients, self.khoa)

    def test_a_form_post_is_not_answered_by_the_page_route(self):
        self.authenticate("hoa.portal", "hoa.portal")
        response = self.url_open("/my/notifications", data={"csrf_token": "wrong"})
        self.assertNotEqual(response.status_code, 200)
