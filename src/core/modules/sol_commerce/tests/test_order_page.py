from odoo.tests import tagged
from odoo.tools.misc import format_date

from .portal_case import PortalCase


@tagged("post_install", "-at_install")
class TestOrderPage(PortalCase):
    """The order page asks before cancelling, keeps its actions in one row and shows the order's dates."""

    def test_cancel_asks_for_confirmation_first(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")

        tree = self.tree(f"/orders/{order.id}")

        cancel = self.find(tree, f"//form[@action='/orders/{order.id}/cancel']")
        self.assertEqual(len(cancel), 1)
        dialog = self.find(cancel[0], "ancestor::div[contains(concat(' ', @class, ' '), ' modal ')]")
        self.assertEqual(len(dialog), 1, "The cancel form is not inside a confirmation dialog.")
        self.assertIn("cannot be undone", dialog[0].text_content())
        opener = self.find(tree, f"//button[@type='button'][@data-bs-target='#{dialog[0].get('id')}']")
        self.assertTrue(opener, "No button opens the confirmation dialog.")
        self.assertEqual(order.order_status, "submitted")

    def test_the_actions_sit_in_one_row(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")

        actions = self.find(self.tree(f"/orders/{order.id}"), "//div[@id='order_actions']")

        self.assertEqual(len(actions), 1)
        self.assertIn("d-flex", actions[0].get("class"))
        self.assertTrue(self.find(actions[0], ".//button[@data-bs-toggle='modal']"))
        self.assertTrue(self.find(actions[0], f".//form[@action='/orders/{order.id}/reorder']"))

    def test_the_page_shows_when_the_order_was_submitted_and_its_deadline(self):
        order = self.sent_order()
        order.submitted_at = order.create_date

        text = self.find(self.tree(f"/orders/{order.id}"), "//dl[@id='order_dates']")[0].text_content()

        self.assertIn("Submitted", text)
        self.assertIn(format_date(self.env, order.submitted_at), text)
        self.assertIn("Quotation deadline", text)
        self.assertIn(format_date(self.env, order.payment_deadline), text)
