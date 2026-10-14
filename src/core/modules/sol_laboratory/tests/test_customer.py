from odoo.exceptions import UserError
from odoo.tests import tagged

from .request_case import RequestCase


@tagged("post_install", "-at_install")
class TestCustomer(RequestCase):
    def test_customer_with_an_open_request_cannot_be_archived(self):
        with self.assertRaises(UserError):
            self.customer.action_archive()

        self.request.action_cancel()
        self.customer.action_archive()
        self.assertFalse(self.customer.active)
