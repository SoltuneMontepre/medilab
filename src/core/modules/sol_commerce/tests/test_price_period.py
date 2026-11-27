from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_PRICE_PERIOD


@tagged("post_install", "-at_install")
class TestPricePeriod(OrderCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.lead_price)
        cls.next_year = cls.today.replace(year=cls.today.year + 1, month=1, day=1)

    def add_period(self, price, start, until=False, parameter_price=None):
        return self.env[MODEL_PRICE_PERIOD].create(
            {
                "parameter_price_id": (parameter_price or self.lead_price).id,
                "list_price": price,
                "valid_from": start,
                "valid_until": until,
            }
        )

    def end_current_period(self, last_day):
        self.lead_price.period_ids.filtered(
            lambda period: bool(period.valid_from and period.valid_from <= self.today)
        ).valid_until = last_day

    def quotation_on(self, day):
        order = self.make_quotable_order()
        order.date_order = datetime.combine(day, datetime.min.time().replace(hour=5))
        return order

    def test_a_price_given_without_periods_applies_from_today(self):
        arsenic = self.create_parameter("Arsenic (As)", self.group)

        price = self.env[MODEL_PARAMETER_PRICE].create(
            {"parameter_id": arsenic.id, "list_price": 60000, "tax_id": self.vat.id}
        )

        period = price.period_ids
        self.assertEqual((period.valid_from, period.valid_until, period.list_price), (self.today, False, 60000))
        self.assertEqual(price.list_price, 60000)

    def test_a_new_period_entered_ahead_does_not_change_today_price(self):
        self.end_current_period(self.next_year - timedelta(days=1))

        self.add_period(170000, self.next_year)

        self.assertEqual(self.lead_price.list_price, 150000)
        self.assertEqual(self.lead_product.list_price, 150000)

    def test_a_quotation_takes_the_price_in_force_on_its_date(self):
        self.end_current_period(self.next_year - timedelta(days=1))
        self.add_period(170000, self.next_year)

        before = self.quotation_on(self.next_year - timedelta(days=1))
        after = self.quotation_on(self.next_year)

        self.assertEqual(before._catalog_lines().price_unit, 150000)
        self.assertEqual(after._catalog_lines().price_unit, 170000)

    def test_a_sent_quotation_keeps_its_price_when_a_new_period_starts(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        self.lead_price.list_price = 190000

        self.assertEqual(order._catalog_lines().price_unit, 150000)

    def test_overlapping_periods_are_refused(self):
        with self.assertRaisesRegex(ValidationError, "overlap"):
            self.add_period(170000, self.today + timedelta(days=30))

    def test_setting_a_price_today_ends_the_current_period_yesterday(self):
        self.lead_price.period_ids.valid_from = self.today - timedelta(days=10)

        self.lead_price.list_price = 160000

        periods = self.lead_price.period_ids.sorted("valid_from")
        self.assertEqual(periods.mapped("valid_until"), [self.today - timedelta(days=1), False])
        self.assertEqual(periods.mapped("list_price"), [150000, 160000])
        self.assertEqual(self.lead_product.list_price, 160000)

    def test_a_parameter_whose_period_ended_is_not_sold(self):
        self.lead_price.period_ids.write({"valid_from": self.today - timedelta(days=10)})

        self.end_current_period(self.today - timedelta(days=1))

        self.assertFalse(self.lead_product.sale_ok)
        self.assertFalse(self.package_product.sale_ok)

    def test_the_daily_refresh_starts_a_period_on_its_day(self):
        self.end_current_period(self.today)
        self.add_period(160000, self.today + timedelta(days=1))

        with freeze_time(self.today + timedelta(days=1, hours=12)):
            self.env[MODEL_PRICE_PERIOD]._refresh_current_prices()

        self.assertEqual(self.lead_price.list_price, 160000)
        self.assertEqual(self.lead_product.list_price, 160000)
        self.assertEqual(self.package.list_price, 160000 + 80000)
