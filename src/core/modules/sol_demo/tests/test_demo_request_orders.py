from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_demo.demo_orders import seed_request_orders
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST


@tagged("post_install", "-at_install")
class TestDemoRequestOrders(TransactionCase):
    def orders_of(self, requests):
        return self.env[MODEL_SALE_ORDER].search([("test_request_id", "in", requests.ids)])

    def test_every_demo_test_request_comes_from_an_order(self):
        requests = self.env[MODEL_TEST_REQUEST].search([])

        self.assertTrue(requests)
        self.assertEqual(self.orders_of(requests).test_request_id, requests)

    def test_a_request_without_an_order_gets_one_in_the_status_it_reached(self):
        customer = self.env.ref("sol_demo.demo_customer_an_phu")
        requests = self.env[MODEL_TEST_REQUEST]
        open_request = requests.create({"customer_id": customer.id})
        cancelled = requests.create({"customer_id": customer.id, "status": "cancelled"})

        seed_request_orders(self.env)
        seed_request_orders(self.env)

        orders = self.orders_of(open_request | cancelled)
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders.filtered(lambda order: order.test_request_id == open_request).order_status, "confirmed")
        self.assertEqual(orders.filtered(lambda order: order.test_request_id == cancelled).order_status, "cancelled")
        self.assertEqual(orders.customer_id, customer.partner_id)
