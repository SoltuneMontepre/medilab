from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MAIL,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MOBILE_DEVICE,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PUSH_DELIVERY,
    MODEL_SCHEDULED_JOB,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    CHANNEL_EMAIL,
    CHANNEL_POPUP,
    CHANNEL_PUSH,
    EVENT_TASK_REMINDER,
)

REMIND = "notifications.remind"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestReminders(SchedulingCase):
    """The tester keeps e-mail and push on for reminders and turned the pop-up off."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"
        cls.event = cls.env[MODEL_MAIL_MESSAGE_SUBTYPE].search([("code", "=", EVENT_TASK_REMINDER)], limit=1)
        user = cls.tester.user_id
        user.partner_id.email = "cuong.le@example.com"
        preferences = cls.env[MODEL_NOTIFICATION_PREFERENCE].with_user(user)
        preferences.set_own(cls.event, CHANNEL_POPUP, False)
        preferences.set_own(cls.event, CHANNEL_EMAIL, True)
        preferences.set_own(cls.event, CHANNEL_PUSH, True)
        cls.device = cls.env[MODEL_MOBILE_DEVICE].with_user(user).register_token("tester-phone", "android")

    def booked(self, test):
        self.testing_task(test, self.tester)
        return self.schedule(test, self.tester)

    def reminders(self, booking):
        return self.env[MODEL_MAIL_MESSAGE].search(
            [("notification_key", "=like", f"calendar:{booking.calendar_event_id.id}:reminder:%")]
        )

    def test_a_booking_starting_within_the_lead_time_is_reminded_once_on_each_channel_kept_on(self):
        booking = self.booked(self.test)
        self.assertEqual(booking.starts_at, MONDAY)
        with patch.object(type(self.tester.user_id), "_bus_send") as sent:
            self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)
            self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)
        message = self.reminders(booking)
        self.assertEqual(len(message), 1)
        self.assertEqual((message.model, message.res_id), (MODEL_TASK, booking.task_id.id))
        on_task = self.env[MODEL_MAIL_MESSAGE].search(
            [
                ("model", "=", MODEL_TASK),
                ("res_id", "=", booking.task_id.id),
                ("notification_key", "=like", "calendar:%"),
            ]
        )
        self.assertEqual(on_task, message)
        partner = self.tester.user_id.partner_id
        notification = message.notification_ids.filtered(lambda item: item.res_partner_id == partner)
        self.assertEqual(len(notification), 1)
        mails = self.env[MODEL_MAIL_MAIL].search(
            [("mail_message_id", "=", message.id), ("email_to", "=", partner.email)]
        )
        self.assertEqual(len(mails), 1)
        self.assertEqual(notification.mail_mail_id, mails)
        pushes = self.env[MODEL_PUSH_DELIVERY].search([("notification_id", "=", notification.id)])
        self.assertEqual(pushes.mobile_device_id, self.device)
        self.assertEqual(len(pushes), 1)
        self.assertNotEqual(notification.notification_type, "inbox")
        self.assertFalse([call for call in sent.call_args_list if call.args[:1] == ("mail.message/inbox",)])

    def test_a_turned_off_event_notifies_nobody_and_turning_it_on_notifies_the_next_booking(self):
        first = self.booked(self.test)
        self.event.enabled = False
        self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)
        self.assertFalse(self.reminders(first))
        self.assertFalse(self.env[MODEL_PUSH_DELIVERY].search([("mobile_device_id", "=", self.device.id)]))

        self.event.enabled = True
        second = self.booked(self.new_test())
        self.assertEqual(second.starts_at, first.ends_at)
        with freeze_time(second.starts_at - timedelta(minutes=5)):
            self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)
        self.assertEqual(len(self.reminders(second)), 1)
        self.assertFalse(self.reminders(first))
