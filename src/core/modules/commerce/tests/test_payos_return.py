from odoo.tests import HttpCase, tagged

from odoo.addons.commerce.constants.payos import CANCEL_ROUTE, RETURN_ROUTE


@tagged("post_install", "-at_install")
class TestPayosReturn(HttpCase):
    def test_the_return_and_cancel_pages_only_inform(self):
        returned = self.url_open(RETURN_ROUTE + "?orderCode=1&status=PAID&code=00")
        cancelled = self.url_open(CANCEL_ROUTE + "?orderCode=1&status=CANCELLED&cancel=true")

        self.assertEqual(returned.status_code, 200)
        self.assertIn("recorded as soon as PayOS confirms it", returned.text)
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn("Payment cancelled", cancelled.text)
