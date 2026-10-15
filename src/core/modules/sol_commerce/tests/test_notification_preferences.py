from odoo.exceptions import UserError
from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_commerce.constants.notifications import (
    EVENT_INVOICE_SENT,
    EVENT_ORDER_UPDATED,
    EVENT_RESULT_RELEASED,
)
from odoo.addons.sol_commerce.constants.orders import STATUS_CLAIMED
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP


@tagged("post_install", "-at_install")
class TestNotificationPreferences(InvoicingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.business = cls.env["res.partner"].create({"name": "An Phu", "is_company": True})
        cls.hoa = cls.contact("Hoa", "hoa@example.com")
        cls.khoa = cls.contact("Khoa", "khoa@example.com")
        cls.hoa_user = cls.portal_user("hoa@example.com", cls.hoa)
        cls.updated = cls.env["mail.message.subtype"]._event(EVENT_ORDER_UPDATED)
        cls.invoice_sent = cls.env["mail.message.subtype"]._event(EVENT_INVOICE_SENT)
        cls.released = cls.env["mail.message.subtype"]._event(EVENT_RESULT_RELEASED)

    @classmethod
    def contact(cls, name, email):
        return cls.env["res.partner"].create(
            {"name": name, "email": email, "parent_id": cls.business.id, "type": "contact"}
        )

    def channels(self, partner, event):
        return self.env["mail.message"]._channels_for(partner, event)

    def test_a_new_customer_is_notified_by_email_without_configuring_anything(self):
        for event in (self.updated, self.released):
            self.assertEqual(self.channels(self.hoa, event), {CHANNEL_EMAIL})

    def test_a_changed_preference_applies_to_the_next_notification_only(self):
        order = self.order.sudo()
        order.partner_id = self.hoa
        order._notify_status(STATUS_CLAIMED)
        sent = self.env["mail.message"].search([("notification_key", "=", f"order:{order.id}:claimed")])
        self.assertEqual(sent.notification_ids.notification_type, "email")
        preferences = self.env["medilab.notification.preference"].with_user(self.hoa_user)
        preferences.set_own(self.updated, CHANNEL_EMAIL, False)
        preferences.set_own(self.updated, CHANNEL_POPUP, True)
        self.assertEqual(self.channels(self.hoa, self.updated), {CHANNEL_POPUP})
        self.assertEqual(sent.notification_ids.notification_type, "email")

    def test_an_event_can_use_several_channels(self):
        preferences = self.env["medilab.notification.preference"].with_user(self.hoa_user)
        preferences.set_own(self.released, CHANNEL_POPUP, True)
        self.assertEqual(self.channels(self.hoa, self.released), {CHANNEL_EMAIL, CHANNEL_POPUP})

    def test_a_mandatory_notification_cannot_be_turned_off(self):
        preferences = self.env["medilab.notification.preference"].with_user(self.hoa_user)
        with self.assertRaises(UserError):
            preferences.set_own(self.invoice_sent, CHANNEL_EMAIL, False)
        self.assertIn(CHANNEL_EMAIL, self.channels(self.hoa, self.invoice_sent))

    def test_an_order_status_is_notified_once(self):
        order = self.order.sudo()
        order.partner_id = self.hoa
        order._notify_status(STATUS_CLAIMED)
        order._notify_status(STATUS_CLAIMED)
        messages = self.env["mail.message"].search([("notification_key", "=", f"order:{order.id}:claimed")])
        self.assertEqual(len(messages), 1)

    def test_a_business_sends_an_event_to_the_contact_it_chose(self):
        routes = self.env["medilab.notification.contact"].with_user(self.hoa_user)
        routes.set_own(self.updated, self.khoa)
        recipients = self.env["mail.message"]._event_partners(self.updated, self.hoa)
        self.assertEqual(recipients, self.khoa)
        other = self.env["mail.message"]._event_partners(self.released, self.hoa)
        self.assertEqual(other, self.hoa)

    def test_a_mandatory_event_also_reaches_the_document_contact(self):
        routes = self.env["medilab.notification.contact"].with_user(self.hoa_user)
        routes.set_own(self.invoice_sent, self.khoa)
        recipients = self.env["mail.message"]._event_partners(self.invoice_sent, self.hoa)
        self.assertEqual(recipients, self.hoa | self.khoa)

    def test_choosing_no_contact_sends_the_event_to_the_document_contact_again(self):
        routes = self.env["medilab.notification.contact"].with_user(self.hoa_user)
        routes.set_own(self.updated, self.khoa)
        routes.set_own(self.updated, self.env["res.partner"])
        recipients = self.env["mail.message"]._event_partners(self.updated, self.hoa)
        self.assertEqual(recipients, self.hoa)

    def test_a_business_cannot_choose_a_contact_of_another_company(self):
        stranger = self.env["res.partner"].create({"name": "Stranger", "email": "s@example.com"})
        routes = self.env["medilab.notification.contact"].with_user(self.hoa_user)
        with self.assertRaises(UserError):
            routes.set_own(self.invoice_sent, stranger)

    def test_the_chosen_contact_is_notified_by_email(self):
        routes = self.env["medilab.notification.contact"].with_user(self.hoa_user)
        routes.set_own(self.updated, self.khoa)
        order = self.order.sudo()
        order.partner_id = self.hoa
        order._notify_status(STATUS_CLAIMED)
        message = self.env["mail.message"].search([("notification_key", "=", f"order:{order.id}:claimed")])
        self.assertEqual(message.notification_ids.res_partner_id, self.khoa)
