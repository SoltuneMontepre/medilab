from odoo.fields import Command
from odoo.tests import TransactionCase


class InvoicingCase(TransactionCase):
    """A confirmed order for 5,000,000 VND with no tax, on the Vietnamese chart."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.chart_template:
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
        cls.order.action_confirm()
        if not cls.env["account.journal"].search(
            [("type", "=", "cash"), ("company_id", "=", company.id)], limit=1
        ):
            cls.env["account.journal"].create(
                {"name": "Cash", "type": "cash", "code": "CSH", "company_id": company.id}
            )

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
