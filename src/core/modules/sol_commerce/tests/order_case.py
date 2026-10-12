from odoo.fields import Command

from .common import PricingCase
from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_PERSON

ORDER_PERMISSIONS = (
    "order.read.all",
    "order.create.all",
    "order.edit.all",
    "cancellation.request.read.all",
    "cancellation.request.edit.all",
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
                    "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
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
        cls.head.write({"group_ids": [Command.link(cls.env.ref(ALL_ORDERS_GROUP).id)]})

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
