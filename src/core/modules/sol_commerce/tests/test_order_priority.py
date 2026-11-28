from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_DISCOUNT
from odoo.addons.sol_commerce.constants.settings import (
    PRIORITY_MIN_DAYS_PARAMETER,
    PRIORITY_ORDERS_PARAMETER,
    PRIORITY_SURCHARGE_PARAMETER,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.models.sample_collection.test_request_estimate import TestRequestEstimate


@tagged("post_install", "-at_install")
class TestOrderPriority(OrderCase):
    """Lead is tested in 5 working days; the samples are picked up 3 working days from now."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter.method_ids.turnaround_days = 5
        cls.other.method_ids.turnaround_days = 5

    def setUp(self):
        super().setUp()
        self.set_param(PRIORITY_SURCHARGE_PARAMETER, 20)

    def set_param(self, key, value):
        self.env["ir.config_parameter"].sudo().set_str(key, str(value))

    def after(self, day, days):
        return self.env[MODEL_TEST_REQUEST]._date_after_working_days(day, days)

    def today(self):
        return self.env[MODEL_SAMPLE_TEST]._local_day(fields.Datetime.now())

    def make_priority_order(self, lines=None):
        """A quotable order picked up in 3 working days whose requested date is 2 working days before its standard
        return date."""
        order = self.make_quotable_order(lines)
        pickup = self.after(self.today(), 3)
        order.expected_collection_date = pickup
        order.requested_date = self.after(pickup, 3)
        return order

    def accept(self, order):
        with patch.object(
            TestRequestEstimate,
            "_check_priority",
            return_value={"date": order.requested_date, "feasible": True, "reasons": []},
        ):
            order.with_user(self.sales).action_accept_priority()

    def surcharge(self, order):
        return order._priority_surcharge_lines()

    def test_a_date_before_the_standard_return_date_is_a_priority_request(self):
        order = self.make_priority_order()

        self.assertEqual(order.standard_return_date, self.after(order.expected_collection_date, 5))
        self.assertEqual(order.priority_request, "requested")

    def test_a_date_on_the_standard_return_date_is_not_a_priority_request(self):
        order = self.make_priority_order()

        order.requested_date = order.standard_return_date

        self.assertFalse(order.priority_request)

    def test_a_longer_turnaround_makes_an_order_a_priority_request(self):
        order = self.make_quotable_order()
        pickup = self.after(self.today(), 3)
        order.write({"expected_collection_date": pickup, "requested_date": self.after(pickup, 5)})
        self.assertFalse(order.priority_request)

        self.parameter.method_ids.turnaround_days = 7
        order._compute_turnaround_days()

        self.assertEqual(order.priority_request, "requested")

    def test_with_priority_orders_off_no_order_becomes_a_priority_request(self):
        self.set_param(PRIORITY_ORDERS_PARAMETER, "off")
        order = self.make_quotable_order()

        self.assertEqual(order._min_requested_date(), order._standard_return_date())
        with self.assertRaisesRegex(UserError, "Choose a date on or after"):
            order._set_portal_dates(self.after(self.today(), 1).isoformat())
        self.assertFalse(order.priority_request)

    def test_a_date_before_the_shortest_priority_turnaround_is_refused(self):
        self.set_param(PRIORITY_MIN_DAYS_PARAMETER, 2)
        order = self.make_quotable_order()
        start = order._estimate_start_day()

        with self.assertRaisesRegex(UserError, "Choose a date on or after"):
            order._set_portal_dates(self.after(start, 1).isoformat())
        order._set_portal_dates(self.after(start, 2).isoformat())

        self.assertEqual(order.priority_request, "requested")

    def test_accepting_priority_adds_the_surcharge_taxed_as_the_lines(self):
        order = self.make_priority_order()
        base = sum(order._catalog_lines().mapped("price_subtotal"))

        self.accept(order)

        line = self.surcharge(order)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.price_subtotal, order.currency_id.round(base * 0.2))
        self.assertEqual(line.tax_ids, order._catalog_lines().tax_ids)
        self.assertIn("20%", line.name or "")
        self.assertFalse(order._catalog_lines() & line)

    def test_declining_priority_adds_no_surcharge(self):
        order = self.make_priority_order()

        order.with_user(self.sales).action_decline_priority()

        self.assertFalse(self.surcharge(order))

    def test_a_surcharge_of_zero_adds_no_line(self):
        self.set_param(PRIORITY_SURCHARGE_PARAMETER, 0)
        order = self.make_priority_order()

        self.accept(order)

        self.assertTrue(order.priority)
        self.assertFalse(self.surcharge(order))

    def test_the_surcharge_follows_the_lines_until_the_quotation_is_sent(self):
        order = self.make_priority_order()
        self.accept(order)

        order._catalog_lines().product_uom_qty = 2

        base = sum(order._catalog_lines().mapped("price_subtotal"))
        self.assertEqual(self.surcharge(order).price_subtotal, order.currency_id.round(base * 0.2))

    def test_a_whole_quotation_discount_does_not_lower_the_surcharge(self):
        order = self.make_priority_order()
        self.accept(order)
        before = self.surcharge(order).price_subtotal

        wizard = (
            self.env[MODEL_SALE_ORDER_DISCOUNT]
            .with_user(self.sales)
            .with_context(active_id=order.id)
            .create({"discount_type": "so_discount", "discount_percentage": 0.1})
        )
        wizard.action_apply_discount()

        self.assertEqual(self.surcharge(order).price_subtotal, before)
        self.assertFalse(self.surcharge(order).discount)

    def test_a_later_requested_date_removes_the_priority_and_its_surcharge(self):
        order = self.make_priority_order()
        self.accept(order)

        order.requested_date = order.standard_return_date

        self.assertFalse(order.priority_request)
        self.assertFalse(order.priority)
        self.assertFalse(self.surcharge(order))
        self.assertEqual(order.committed_date, order._earliest_return_date())

    def test_a_changed_surcharge_applies_to_unsent_quotations_only(self):
        sent = self.make_priority_order()
        self.accept(sent)
        sent.with_user(self.sales).action_send_quotation()
        unsent = self.make_priority_order()
        self.accept(unsent)
        sent_amount = self.surcharge(sent).price_subtotal

        self.env["res.config.settings"].create({"priority_surcharge_percent": 30}).execute()

        base = sum(unsent._catalog_lines().mapped("price_subtotal"))
        self.assertEqual(self.surcharge(unsent).price_subtotal, unsent.currency_id.round(base * 0.3))
        self.assertEqual(self.surcharge(sent).price_subtotal, sent_amount)

    def test_the_priority_settings_refuse_values_out_of_range(self):
        settings = self.env["res.config.settings"]
        with self.assertRaises(ValidationError):
            settings.create({"priority_surcharge_percent": 120})
        with self.assertRaises(ValidationError):
            settings.create({"priority_min_turnaround_days": 0})

    def test_the_cart_shows_the_surcharge_of_an_early_date(self):
        order = self.make_quotable_order()
        early = self.after(order._estimate_start_day(), 1)

        window = order._cart_priority_window(early.isoformat())

        self.assertTrue(window["priority"])
        self.assertEqual(window["surcharge"], order.currency_id.round(order.catalog_total * 0.2))
        self.assertFalse(order._cart_priority_window((window["standard"] + timedelta(days=1)).isoformat())["priority"])
