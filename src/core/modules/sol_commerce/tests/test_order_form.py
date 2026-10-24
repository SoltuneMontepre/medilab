from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER

# Odoo's own order actions that go around MediLab's quotation, confirmation and cancellation.
ODOO_HEADER_ACTIONS = (
    "action_quotation_send",
    "action_confirm",
    "sale.action_report_saleorder",
    "action_preview_sale_order",
    "action_cancel",
    "action_draft",
)
HIDDEN = ("1", "True")


@tagged("post_install", "-at_install")
class TestOrderForm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.arch = etree.fromstring(cls.env[MODEL_SALE_ORDER].get_view(view_type="form")["arch"])

    def _nodes(self, path, **variables):
        found = self.arch.xpath(path, **variables)
        assert isinstance(found, list)
        return [node for node in found if isinstance(node, etree._Element)]

    def test_header_shows_no_odoo_order_action(self):
        for name in ODOO_HEADER_ACTIONS:
            for button in self._nodes("//header/button[@name=$name]", name=name):
                with self.subTest(name=name, string=button.get("string")):
                    self.assertIn(button.get("invisible"), HIDDEN)

    def test_header_shows_one_status_bar(self):
        bars = self._nodes("//header/field[@widget='statusbar']")
        visible = [bar.get("name") for bar in bars if bar.get("invisible") not in HIDDEN]
        self.assertEqual(visible, ["order_status"])

    def test_customer_comes_before_its_contact(self):
        names = [
            field.get("name") for field in self._nodes("//sheet//field[@name='customer_id' or @name='partner_id']")
        ]
        self.assertEqual(names[:2], ["customer_id", "partner_id"])

    def test_contact_is_hidden_for_an_individual(self):
        contact = self._nodes("//sheet//field[@name='partner_id']")[0]
        self.assertEqual(contact.get("invisible"), "customer_id and not customer_is_company")
        self.assertIn("not customer_id", contact.get("readonly") or "")

    def test_only_customers_can_be_chosen(self):
        customer = self._nodes("//sheet//field[@name='customer_id']")[0]
        self.assertEqual(customer.get("domain"), "[('customer_ids', '!=', False)]")

    def test_form_shows_no_price_list(self):
        for node in self._nodes("//sheet//*[@name='pricelist_id' or @for='pricelist_id']"):
            with self.subTest(tag=node.tag):
                parent = node.getparent()
                hidden = node.get("invisible") in HIDDEN or (parent is not None and parent.get("invisible") in HIDDEN)
                self.assertTrue(hidden)

    def test_vietnamese_tells_customer_and_contact_apart(self):
        fields = self.env[MODEL_SALE_ORDER].with_context(lang="vi_VN").fields_get(["customer_id", "partner_id"])
        self.assertEqual(fields["customer_id"]["string"], "Khách Hàng")
        self.assertEqual(fields["partner_id"]["string"], "Liên Hệ")
