from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_TEMPLATE, MODEL_ORDER_TEMPLATE_SAVE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderTemplateBase
else:
    SaleOrderTemplateBase = object


# Đơn Hàng: saves catalog selections and keeps the unavailable selections of template reuse.
class SaleOrderTemplate(models.Model, SaleOrderTemplateBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Names and reasons of template selections omitted when this order was created.
        template_omission_note = fields.Text(readonly=True, copy=False, groups="base.group_user")

        # Whether the current user can save this assigned order as a template.
        can_save_order_template = fields.Boolean(compute="_compute_can_save_order_template")

    @api.depends("user_id", "customer_id")
    @api.depends_context("uid")
    def _compute_can_save_order_template(self):
        allowed = self.env[MODEL_ORDER_TEMPLATE]._has_permission("create")
        broad = self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP)
        for order in self:
            order.can_save_order_template = bool(
                allowed and order.customer_id and (broad or order.user_id == self.env.user)
            )

    def action_save_as_template(self):
        self.ensure_one()
        self.env[MODEL_ORDER_TEMPLATE]._check_source(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_ORDER_TEMPLATE_SAVE,
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def _save_as_template(self, name):
        self.ensure_one()
        templates = self.env[MODEL_ORDER_TEMPLATE]
        templates._check_source(self)
        lines = self._catalog_lines()
        if not lines:
            raise ValidationError(self.env._("Add at least one catalog selection before saving a template."))
        fractional = lines.filtered(lambda line: not float(line.product_uom_qty).is_integer())
        if fractional:
            raise ValidationError(
                self.env._(
                    "A template orders whole quantities. Change the quantity of these lines to a whole number:\n%s",
                    "\n".join(name or "" for name in fractional.mapped("product_id.display_name")),
                )
            )
        return templates.create(
            {
                "name": name,
                "source_order_id": self.id,
                "customer_id": self._customer_record().id,
                "line_ids": [
                    Command.create({"product_id": line.product_id.product_tmpl_id.id, "quantity": line.product_uom_qty})
                    for line in lines
                ],
            }
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_template_source(self):
        if (
            self.env[MODEL_ORDER_TEMPLATE]
            .sudo()
            .with_context(active_test=False)
            .search_count([("source_order_id", "in", self.ids)])
        ):
            raise UserError(self.env._("This order is the source of an order template. Delete the template first."))
