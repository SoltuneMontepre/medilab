from odoo.fields import Command

from .common import PricingCase
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ORDER_SAMPLE,
    MODEL_PARAMETER_PRICE,
    MODEL_PRODUCT_TEMPLATE,
)
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_ROLE,
    MODEL_SAMPLE_TYPE,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

ORDER_PERMISSIONS = (
    "order.read.own",
    "order.create.all",
    "order.edit.own",
    "cancellation.request.read.all",
    "cancellation.request.edit.all",
    "order.sample.read.all",
    "order.sample.create.all",
    "order.sample.edit.all",
    "order.sample.delete.all",
    "quotation.read.all",
    "customer.sales.terms.read.all",
    "customer.sales.terms.create.all",
    "customer.sales.terms.edit.all",
)


class OrderCase(PricingCase):
    """A priced parameter, a cheaper package, a portal customer and two salespeople."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.other_price = cls.env[MODEL_PARAMETER_PRICE].create(
            {"parameter_id": cls.other.id, "list_price": 80000, "tax_id": cls.vat.id}
        )
        cls.package = cls.create_package(100000, (cls.parameter, 1), (cls.other, 1))
        products = cls.env[MODEL_PRODUCT_TEMPLATE]
        cls.lead_product = products.search([("parameter_id", "=", cls.parameter.id)], limit=1)
        cls.package_product = products.search([("service_package_id", "=", cls.package.id)], limit=1)
        cls.sample_type = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled water", "code": "LM-QUOTE"})
        cls.offer(cls.parameter, cls.sample_type)
        cls.offer(cls.other, cls.sample_type)
        cls.customer = cls.env["res.partner"].create({"name": "Cong ty Nuoc Sach", "is_company": True})
        cls.contact = cls.env["res.partner"].create(
            {"name": "Pham Thi Hoa", "parent_id": cls.customer.id, "email": "hoa@nuocsach.example"}
        )
        cls.portal = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Pham Thi Hoa",
                    "login": "portal.hoa",
                    "partner_id": cls.contact.id,
                    "group_ids": [Command.set([persisted_id(cls.env.ref("base.group_portal"))])],
                }
            )
        )
        permissions = cls.env[MODEL_PERMISSION].search([("code", "in", ORDER_PERMISSIONS)])
        cls.sales_person = cls.env[MODEL_PERSON].create({"name": "Nguyen Thi Thu", "login": "sales.orders"})
        cls.other_person = cls.env[MODEL_PERSON].create({"name": "Le Van Nam", "login": "sales.other"})
        cls.head_person = cls.env[MODEL_PERSON].create({"name": "Tran Quoc Bao", "login": "sales.head"})
        for person in (cls.sales_person, cls.other_person, cls.head_person):
            person.permission_ids = permissions
        cls.sales = cls.sales_person.user_id
        cls.other_sales = cls.other_person.user_id
        cls.head = cls.head_person.user_id
        cls.head.write({"group_ids": [Command.link(persisted_id(cls.env.ref(ALL_ORDERS_GROUP)))]})
        cls.customer_record = cls.env[MODEL_CUSTOMER].create({"partner_id": cls.customer.id})
        cls.setup_roles()

    @classmethod
    def setup_roles(cls):
        """Both salespeople hold a Sales role and the Head of Sales theirs; neither role grants a permission."""
        sales_role = cls.env[MODEL_ROLE].create({"code": "qo_sales", "name": "Sales"})
        cls.sales_person.role_ids = sales_role
        cls.other_person.role_ids = sales_role
        cls.head_person.role_ids = cls.env[MODEL_ROLE].create({"code": "qo_head", "name": "Head of Sales"})

    def make_order(self, lines, status="draft", **vals):
        return self.env["sale.order"].create(
            {
                "partner_id": self.contact.id,
                "customer_id": self.customer.id,
                "source": "portal",
                "order_status": status,
                "user_id": False,
                "order_line": [
                    Command.create({"product_id": product.product_variant_ids.id, "product_uom_qty": quantity})
                    for product, quantity in lines
                ],
                **vals,
            }
        )

    def make_sample(self, order, name="Lavie bottled water 1 L"):
        return self.env[MODEL_ORDER_SAMPLE].create(
            {
                "order_id": order.id,
                "customer_sample_name": name,
                "sample_type_id": self.sample_type.id,
                "physical_state": "liquid",
            }
        )

    def make_quotable_order(self, lines=None):
        """A claimed order of the first salesperson whose catalog lines are all tested on one sample."""
        order = self.make_order(
            lines or [(self.lead_product, 1)],
            status="claimed",
            user_id=self.sales.id,
            advance_method="cash",
            advance_mode="full",
        )
        order._catalog_lines().sample_id = self.make_sample(order)
        return order

    def pay_advance(self, order):
        """Register an ordinary Odoo payment of the order's advance invoice."""
        invoices = order.sudo().invoice_ids.filtered(
            lambda invoice: invoice.state == "posted" and invoice.payment_state == "not_paid"
        )
        self.env["account.payment.register"].with_context(active_model="account.move", active_ids=invoices.ids).create(
            {}
        ).action_create_payments()

    def make_confirmed_order(self, lines=None):
        """A quotable order whose advance was paid and that sales confirmed."""
        order = self.make_quotable_order(lines)
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        return order

    def sent_order(self):
        """A quotable order whose quotation sales sent."""
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        return order
