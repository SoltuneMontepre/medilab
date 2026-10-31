from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.notifications import EVENT_RESULT_RELEASED
from odoo.addons.sol_laboratory.constants.models import MODEL_NOTIFICATION_PREFERENCE, MODEL_TEST_REPORT
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP
from odoo.addons.sol_laboratory.tests.change_request_case import ChangeRequestCase


@tagged("post_install", "-at_install")
class TestOrderTracking(ChangeRequestCase):
    """An order follows its test request through testing, and its contact is told once for each issued report,
    through the channels they chose, when the results are released."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create(
            {"name": "Bui Thi Mai", "parent_id": cls.customer.partner_id.id, "email": "mai@anphu.example"}
        )
        cls.order = cls.env[MODEL_SALE_ORDER].create(
            {
                "partner_id": cls.contact.id,
                "customer_id": cls.customer.partner_id.id,
                "source": "sales",
                "order_status": "confirmed",
                "user_id": cls.create_person("Nguyen Thi Thu", login="thu.tracking").user_id.id,
                "test_request_id": cls.request.id,
            }
        )
        cls.contact_user = new_test_user(cls.env, "mai.portal", groups="base.group_portal", partner_id=cls.contact.id)
        cls.released = cls.env["mail.message.subtype"]._event(EVENT_RESULT_RELEASED)

    def progress(self):
        self.order.invalidate_recordset(["customer_status"])
        return self.order.customer_status

    def released_messages(self):
        return self.messages(self.order).filtered(lambda message: message.subtype_id == self.released)

    def choose(self, channel, enabled):
        self.env[MODEL_NOTIFICATION_PREFERENCE].with_user(self.contact_user).set_own(self.released, channel, enabled)

    def release(self):
        self.complete()
        self.sign()
        return self.released_messages()

    def test_the_order_shows_waiting_testing_then_completed_and_completes_with_the_report(self):
        self.assertEqual(self.progress(), "waiting")

        result = self.enter()
        self.assertEqual(self.progress(), "testing")

        self.send(result)
        self.approve(result)
        self.assertEqual((self.request.status, self.progress()), ("completed", "completed"))
        self.assertEqual(self.order.order_status, "confirmed")

        self.sign()
        self.assertEqual((self.order.order_status, self.progress()), ("completed", "completed"))

    def test_a_cancellation_request_cannot_cancel_an_order_whose_results_are_released(self):
        cancellation = self.order.action_request_cancellation("We no longer need the tests.")
        self.complete()
        self.sign()

        with self.assertRaises(UserError):
            cancellation.action_accept()
        self.assertEqual(self.order.order_status, "completed")

    def test_the_orders_contact_is_told_once_on_the_order_when_the_results_are_released(self):
        self.complete()
        report = self.report()

        self.sign(report)
        report._notify_issued()

        on_order = self.released_messages()
        self.assertEqual(len(on_order), 1)
        self.assertEqual(on_order.notification_ids.res_partner_id, self.contact)
        self.assertIn(self.order.name, (on_order.body or ""))
        issued = self.env.ref("sol_laboratory.event_test_report_issued")
        self.assertFalse(self.messages(report).filtered(lambda message: message.subtype_id == issued))

    def test_the_contact_is_told_only_through_the_channels_they_chose(self):
        self.choose(CHANNEL_EMAIL, False)
        self.choose(CHANNEL_POPUP, True)

        notification = self.release().notification_ids

        self.assertEqual(notification.notification_type, "inbox")
        self.assertFalse(notification.mail_mail_id)

    def test_a_new_version_of_the_report_tells_the_contact_again(self):
        first = self.release()
        change = self.raise_on(
            self.report(),
            person=self.courier,
            change="Reissue the report with the customer's new registered name.",
            reason="The customer changed its business registration.",
        )
        self.sign(change)

        self.sign(self.env[MODEL_TEST_REPORT].browse(change.new_document_id))

        self.assertEqual(len(self.released_messages() - first), 1)
