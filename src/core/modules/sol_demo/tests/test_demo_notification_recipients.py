from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE
from odoo.addons.sol_commerce.constants.notifications import EVENT_INVOICE_OVERDUE
from odoo.addons.sol_demo.demo_orders import _xml_id
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.46.0" / "post-migrate.py"
LEGACY_RECIPIENT = "demo_notification_event_recipient_department"


@tagged("post_install", "-at_install")
class TestDemoNotificationRecipients(TransactionCase):
    def assert_overdue_invoice_audience(self):
        invoice = reference_as(self.env[MODEL_ACCOUNT_MOVE], "sol_demo.demo_account_move_overdue")
        users = self.env[MODEL_RES_USERS]
        accountant = reference_as(users, "sol_demo.demo_res_users_accountant")
        sales = reference_as(users, "sol_demo.demo_res_users_sales") | reference_as(
            users, "sol_demo.demo_res_users_sales_2"
        )
        chemistry = reference_as(users, "sol_demo.demo_res_users_chemistry_tester")
        (accountant | sales | chemistry).notification_type = "inbox"

        message = self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_INVOICE_OVERDUE, invoice, "test:demo:overdue", "Invoice overdue", partners=invoice.partner_id
        )
        self.assertEqual(message.notification_ids.res_partner_id, (accountant | sales).partner_id | invoice.partner_id)

    def test_seed_reaches_accounting_sales_and_the_customer(self):
        self.assert_overdue_invoice_audience()

    def test_upgrade_removes_the_legacy_chemistry_recipient(self):
        event = reference_as(self.env[MODEL_MAIL_MESSAGE_SUBTYPE], "sol_commerce.event_invoice_overdue")
        chemistry = reference_as(self.env[MODEL_DEPARTMENT], "sol_demo.demo_hr_department_chemistry")
        recipients = self.env[MODEL_NOTIFICATION_EVENT_RECIPIENT]
        legacy = reference_as(recipients, f"sol_demo.{LEGACY_RECIPIENT}", raise_if_not_found=False)
        if not legacy:
            legacy = recipients.create({"department_id": chemistry.id, "event_id": event.id})
            _xml_id(self.env, LEGACY_RECIPIENT, legacy)

        self.assertTrue(POST_MIGRATE.is_file(), "The demo recipient upgrade migration must exist.")
        migration = load_script(str(POST_MIGRATE), "demo_notification_recipients_post")
        migration.migrate(self.env.cr, "20.0.1.45.0")
        migration.migrate(self.env.cr, "20.0.1.45.0")
        self.env.invalidate_all()

        self.assertFalse(legacy.exists())
        self.assert_overdue_invoice_audience()
