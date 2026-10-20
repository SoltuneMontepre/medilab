from datetime import date, datetime
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import format_date

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_CONTAINER_SCAN,
    MODEL_STOCK_LOT,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED, CONTAINER_SEALED
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT


@tagged("post_install", "-at_install")
class TestContainerOpening(ContainersCase):
    def test_opening_records_who_when_and_the_usable_date(self):
        usable = self.day(10)
        container = self.put_container(self.acid, 500, "Open1", self.env[MODEL_STOCK_PACKAGE]._at_utc(usable))

        self.as_tester(container).action_open()

        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(container.opened_by_id, self.tester.user_id)
        self.assertTrue(container.opened_at)
        # The lot expires in 10 days and the shelf life after opening is 30, so the lot wins.
        self.assertEqual(container.usable_until, usable)

    def test_opening_one_of_five_leaves_the_other_four_sealed(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        usable = self.day(40)
        lot = self.env[MODEL_STOCK_LOT].create(
            {
                "name": "Five",
                "product_id": self.acid.id,
                "company_id": self.env.company.id,
                "expiration_date": packages._at_utc(usable),
            }
        )
        containers = packages.create([{"name": f"Five-0{number}"} for number in range(1, 6)])
        for container in containers:
            self.env[MODEL_STOCK_QUANT]._update_available_quantity(
                self.acid, self.pesticides_store, 100, lot_id=lot, package_id=container
            )

        self.as_tester(containers[0]).action_open()

        self.assertEqual(containers[0].status, CONTAINER_OPENED)
        self.assertEqual(set(containers[1:].mapped("status")), {CONTAINER_SEALED})
        self.assertEqual(set(containers[1:].mapped("usable_until")), {usable})

    def test_an_expired_container_in_another_store_or_without_permission_stays_sealed(self):
        expired = self.put_container(self.acid, 500, "Expired", self.env[MODEL_STOCK_PACKAGE]._at_utc(self.day(-2)))
        elsewhere = self.put_container(self.acid, 500, "Central", location=self.central)
        own = self.put_container(self.acid, 500, "Own")
        with self.assertRaises(UserError):
            self.as_tester(expired).action_open()
        with self.assertRaises(UserError):
            self.as_tester(elsewhere).action_open()
        with self.assertRaises(AccessError):
            self.as_person(own, self.chemist).action_open()
        self.assertEqual(set((expired | elsewhere | own).mapped("status")), {CONTAINER_SEALED})

    def test_a_second_container_of_an_item_waits_until_the_opened_one_is_finished(self):
        first = self.put_container(self.acid, 500, "First")
        second = self.put_container(self.acid, 500, "Second")
        self.as_tester(first).action_open()

        with self.assertRaises(UserError) as waiting:
            self.as_tester(second).action_open()
        self.assertIn(first.name, waiting.exception.args[0])
        self.assertEqual(second.status, CONTAINER_SEALED)

        self.as_tester(first).action_mark_empty()
        self.as_tester(second).action_open()

        self.assertEqual(second.status, CONTAINER_OPENED)

    def test_an_opened_container_of_another_store_or_past_its_date_does_not_hold_back_an_opening(self):
        self.put_container(self.acid, 500, "Other store", location=self.chemistry_store, status=CONTAINER_OPENED)
        self.put_container(
            self.acid, 500, "Past", self.env[MODEL_STOCK_PACKAGE]._at_utc(self.day(-1)), status=CONTAINER_OPENED
        )
        self.put_container(self.water, 500, "Water", status=CONTAINER_OPENED)
        container = self.put_container(self.acid, 500, "Fresh")

        self.as_tester(container).action_open()

        self.assertEqual(container.status, CONTAINER_OPENED)

    def test_an_item_without_a_shelf_life_after_opening_keeps_the_lot_expiry(self):
        self.acid.use_shelf_life_after_opening = False
        container = self.put_container(self.acid, 500, "Kept")

        self.as_tester(container).action_open()

        self.assertEqual(container.usable_until, self.day(30))

    def test_a_shelf_life_of_zero_days_ends_on_the_opening_day(self):
        self.acid.shelf_life_after_opening_days = 0
        container = self.put_container(self.acid, 500, "Today")

        self.as_tester(container).action_open()

        self.assertEqual(container.usable_until, self.day(0))
        with patch.object(type(container), "_today", return_value=self.day(1)):
            with self.assertRaises(UserError):
                container._check_usable()

    def test_a_lot_without_an_expiry_is_not_expired(self):
        container = self.put_container(self.acid, 500, "Undated", expiration=False)
        self.assertFalse(container.usable_until)

        self.as_tester(container).action_open()

        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(container.usable_until, self.day(30))

    def test_the_label_names_who_opened_the_container(self):
        container = self.put_container(self.acid, 500, "Label")
        self.as_tester(container).action_open()

        for report in (CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT):
            html = self.env["ir.actions.report"]._render_qweb_html(report, container.ids)[0].decode()
            self.assertIn("Opened", html)
            self.assertIn(self.tester.name, html)
            self.assertIn(format_date(self.env, container.opened_on), html)

    def test_the_label_dates_the_opening_in_the_laboratory_time_zone(self):
        self.env.company.tz = "Asia/Ho_Chi_Minh"
        container = self.put_container(self.acid, 500, "Night", status=CONTAINER_OPENED)
        # 02:30 on the 19th in Ho Chi Minh City.
        container.sudo().opened_at = datetime(2026, 10, 18, 19, 30)

        html = self.env["ir.actions.report"]._render_qweb_html(CONTAINER_LABEL_REPORT, container.ids)[0].decode()

        self.assertEqual(container.opened_on, date(2026, 10, 19))
        self.assertIn(format_date(self.env, date(2026, 10, 19)), html)
        self.assertNotIn(format_date(self.env, date(2026, 10, 18)), html)

    def test_scanning_a_code_opens_that_container(self):
        container = self.put_container(self.acid, 500, "Scan")
        scan = self.env[MODEL_CONTAINER_SCAN].with_user(self.tester.user_id)

        with self.assertRaises(UserError) as unknown:
            scan.create({"code": "NO-SUCH"}).action_confirm()
        self.assertIn("NO-SUCH", unknown.exception.args[0])

        scan.create({"code": container.name}).action_confirm()

        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(container.opened_by_id, self.tester.user_id)
