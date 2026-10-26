from ast import literal_eval

from lxml import etree

from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import (
    MODEL_PRODUCT_PRODUCT,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SALE_ORDER,
    MODEL_SALE_ORDER_LINE,
)

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
LINE_FORM = "//field[@name='order_line']/form"


@tagged("post_install", "-at_install")
class TestOrderForm(OrderCase):
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

    def test_customer_and_contact_cannot_be_created_from_the_order(self):
        for name in ("customer_id", "partner_id"):
            with self.subTest(name=name):
                field = self._nodes("//sheet//field[@name=$name]", name=name)[0]
                self.assertTrue(literal_eval(field.get("options")).get("no_create"))

    def test_vietnamese_tells_customer_and_contact_apart(self):
        fields = self.env[MODEL_SALE_ORDER].with_context(lang="vi_VN").fields_get(["customer_id", "partner_id"])
        self.assertEqual(fields["customer_id"]["string"], "Khách Hàng")
        self.assertEqual(fields["partner_id"]["string"], "Liên Hệ")

    def test_lines_offer_no_section_note_or_odoo_catalog(self):
        for view in ("list", "kanban"):
            with self.subTest(view=view):
                controls = self._nodes(f"//field[@name='order_line']/{view}/control/*")
                self.assertEqual({control.get("name") for control in controls}, {"add_product_control"})
        self.assertFalse(self._nodes("//widget[@name='combo_menu']"))

    def test_line_is_a_parameter_or_package_on_a_sample(self):
        shown = self._nodes("//list[@name='sol_list']/column[@name='product_and_description']/field")
        names = [field.get("name") for field in shown if field.get("invisible") not in HIDDEN]
        self.assertEqual(names, ["product_template_id"])
        product = shown[0]
        self.assertNotIn("optional", product.attrib)
        self.assertIn("('parameter_id', '!=', False)", product.get("domain"))
        self.assertIn("('service_package_id', '!=', False)", product.get("domain"))
        columns = [child.get("name") for child in self._nodes("//list[@name='sol_list']/*")]
        self.assertEqual(columns[columns.index("product_and_description") + 1], "sample_id")
        delivered = self._nodes("//list[@name='sol_list']/column[field[@name='qty_delivered']]")
        self.assertEqual(delivered[0].get("column_invisible"), "1")

    def test_line_domain_offers_only_parameters_and_packages(self):
        plain = self.env[MODEL_PRODUCT_TEMPLATE].create({"name": "Courier fee"})
        cases = (
            (MODEL_PRODUCT_TEMPLATE, "//list[@name='sol_list']//field[@name='product_template_id']", lambda p: p),
            (MODEL_PRODUCT_PRODUCT, f"{LINE_FORM}//field[@name='product_id']", lambda p: p.product_variant_id),
        )
        for model, path, variant in cases:
            with self.subTest(model=model):
                offered = self.env[model].search(literal_eval(self._nodes(path)[0].get("domain")))
                self.assertIn(variant(self.lead_product), offered)
                self.assertIn(variant(self.package_product), offered)
                self.assertNotIn(variant(plain), offered)
                self.assertFalse(offered.filtered(lambda p: not (p.parameter_id or p.service_package_id)))

    def test_line_form_follows_the_list(self):
        product = self._nodes(f"{LINE_FORM}//field[@name='product_id']")[0]
        self.assertEqual(literal_eval(product.get("options")), {"no_create": True, "no_open": True})
        sample = self._nodes(f"{LINE_FORM}//field[@name='sample_id']")[0]
        self.assertEqual(sample.get("domain"), "[('order_id', '=', parent.id)]")
        self.assertTrue(literal_eval(sample.get("options")).get("no_create"))
        for path in (
            f"{LINE_FORM}/group/group/field[@name='name']",
            f"{LINE_FORM}//label[@for='qty_delivered']",
            f"{LINE_FORM}//div[@name='delivered_qty']",
        ):
            with self.subTest(path=path):
                self.assertIn(self._nodes(path)[0].get("invisible"), HIDDEN)

    def test_form_shows_no_tax_included_switch(self):
        for field in self._nodes("//field[@name='document_tax_mode']"):
            with self.subTest(id=field.get("id")):
                self.assertIn(field.get("invisible"), HIDDEN)

    def test_notebook_leads_with_lines_samples_and_revisions(self):
        pages = [page.get("name") for page in self._nodes("//notebook/page")]
        self.assertEqual(pages[:3], ["order_lines", "samples", "revisions"])

    def test_salesperson_sits_with_the_order_dates(self):
        self.assertTrue(self._nodes("//group[@name='order_details']/field[@name='user_id']"))
        self.assertFalse(self._nodes("//group[@name='sales_person']/field[@name='user_id']"))

    def test_line_without_a_product_has_no_tax(self):
        order = self.env[MODEL_SALE_ORDER].create({"partner_id": self.env.user.partner_id.id})
        line = self.env[MODEL_SALE_ORDER_LINE].create({"order_id": order.id, "name": "Empty line"})
        self.assertFalse(line.tax_ids)
