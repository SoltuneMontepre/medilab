from odoo.fields import Command
from odoo.tests import TransactionCase

from odoo.addons.sol_commerce.models.orders.sale_order_confirmation import SaleOrderConfirmation


class InvoicingCase(TransactionCase):
    """A confirmed order for 5,000,000 VND with no tax, on the Vietnamese chart."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        # Installing account loads Odoo's generic chart in USD when no localisation is guessed; VND has no decimals.
        if company.chart_template != "vn":
            cls.env["account.chart.template"].try_loading("vn", company)
        cls.partner = cls.env["res.partner"].create({"name": "Nguyen Van An"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Lead test",
                "type": "service",
                "list_price": 5_000_000,
                "taxes_id": [Command.clear()],
                "invoice_policy": "order",
            }
        )
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 5_000_000,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        # A portal draft drops the salesperson. The invoice still needs one, so a rejected payment can tell them.
        cls.order.write({"user_id": cls.env.user.id})
        cls.confirm_sale(cls.order)
        if not cls.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", company.id)], limit=1
        ):
            cls.env["account.journal"].create(
                {"name": "Cash", "type": "cash", "code": "CSH", "company_id": company.id}
            )

    @classmethod
    def confirm_sale(cls, order):
        """Odoo's confirmation. These orders are invoices under test, not accepted quotations."""
        # This class is not on the order, so super() cannot skip SaleOrderConfirmation.
        parents = type(order).__mro__
        following = parents[parents.index(SaleOrderConfirmation) + 1 :]
        for parent in following:
            confirm = parent.__dict__.get("action_confirm")
            if confirm:
                return confirm(order)
        raise AttributeError("action_confirm")

    @classmethod
    def portal_user(cls, login, partner):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "password": login,
                "partner_id": partner.id,
                "group_ids": [Command.set(cls.env.ref("base.group_portal").ids)],
            }
        )
