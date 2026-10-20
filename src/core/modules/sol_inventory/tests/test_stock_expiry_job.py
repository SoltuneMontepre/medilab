from datetime import timedelta

from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.jobs import STOCK_EXPIRY_JOB
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_PACKAGE
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED, LOT_AVAILABLE, LOT_EXPIRED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)


@tagged("post_install", "-at_install")
class TestStockExpiryJob(StockCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pesticides_store.manager_id = cls.tester.employee_id
        # Alerts reach the manager in the application.
        cls.tester.user_id.notification_type = "inbox"
        cls.job = cls.env[MODEL_SCHEDULED_JOB].search([("key", "=", STOCK_EXPIRY_JOB)])

    def notices(self, record):
        return (
            self.env[MODEL_MAIL_MESSAGE]
            .search([("model", "=", record._name), ("res_id", "=", record.id)])
            .filtered("notification_key")
        )

    def container(self, lot_name, days, **kwargs):
        packages = self.env[MODEL_STOCK_PACKAGE]
        return self.put_container(self.acid, 400, lot_name, expiration=packages._at_utc(self.day(days)), **kwargs)

    def test_an_expired_lot_is_marked_expired_and_notified_once(self):
        lot = self.container("Expired", -1).lot_id

        self.job._run_batch()
        self.job._run_batch()

        self.assertEqual(lot.status, LOT_EXPIRED)
        notice = self.notices(lot)
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.notification_key, f"stock.expired:lot:{lot.id}")
        self.assertIn(self.tester.user_id.partner_id, notice.notification_ids.res_partner_id)
        self.assertIn("Pesticide residues store", notice.body)

    def test_a_lot_expiring_within_the_warning_is_notified(self):
        soon = self.container("Soon", 10).lot_id
        later = self.container("Later", 60).lot_id

        self.job._run_batch()

        self.assertEqual(soon.status, LOT_AVAILABLE)
        self.assertEqual(self.notices(soon).notification_key, f"stock.expiring:lot:{soon.id}")
        self.assertFalse(self.notices(later))

    def test_a_container_opened_past_its_shelf_life_is_notified_apart_from_its_lot(self):
        container = self.container("Opened", 365, status=CONTAINER_OPENED)
        container.opened_at = container.opened_at.replace(year=container.opened_at.year - 1)

        self.job._run_batch()

        self.assertEqual(self.notices(container).notification_key, f"stock.expired:container:{container.id}")
        self.assertFalse(self.notices(container.lot_id))
        self.assertEqual(container.lot_id.status, LOT_AVAILABLE)

    def test_the_expiry_warning_sets_when_lots_are_listed_as_expiring(self):
        lot = self.container("Warned", 20).lot_id

        self.env[MODEL_RES_CONFIG_SETTINGS].create({"expiry_warning_days": 7}).execute()

        self.assertEqual(self.acid.alert_time, 7)
        self.assertEqual(lot.alert_date, lot.expiration_date - timedelta(days=7))
        self.job._run_batch()
        self.assertFalse(self.notices(lot))

    def test_odoo_schedules_no_activity_of_its_own_for_the_lots_of_stock_items(self):
        lot = self.container("Alert", 5).lot_id

        self.env[MODEL_STOCK_LOT]._alert_date_exceeded()

        self.assertFalse(lot.activity_ids)

    def test_new_stock_items_take_the_expiry_warning(self):
        item = self.create_item("Swabs", "consumable", "lot")

        self.assertEqual(item.alert_time, 30)
