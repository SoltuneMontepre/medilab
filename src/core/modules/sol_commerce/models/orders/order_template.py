from contextvars import ContextVar

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_TEMPLATE, MODEL_ORDER_TEMPLATE_LINE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
)

NOT_IN_OPERATOR = "not in"
CREATING_TEMPLATE_IDS = ContextVar("creating_order_template_ids", default=frozenset())
EDITING_TEMPLATE_IDS = ContextVar("editing_order_template_ids", default=frozenset())


# Đơn Hàng Mẫu
class OrderTemplate(models.Model):
    _name = MODEL_ORDER_TEMPLATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Order Template"
    _order = "name, id"
    _audit_children = ("line_ids",)

    # The customer whose selections were saved.
    customer_id = fields.Many2one(MODEL_CUSTOMER, required=True, ondelete="cascade", index=True, readonly=True)
    # The original order; its current assignment and read access authorize template operations.
    source_order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="restrict", index=True, readonly=True)
    # The name Sales gives the reusable selection.
    name = fields.Char(required=True, index="trigram")
    # False when the template is archived.
    active = fields.Boolean(default=True)
    # The parameters and whole packages to order again.
    line_ids = fields.One2many(MODEL_ORDER_TEMPLATE_LINE, "template_id", string="Selections")
    # Whether the source still belongs to the saved customer; searched against live database relationships.
    source_customer_matches = fields.Boolean(
        compute="_compute_source_customer_matches", search="_search_source_customer_matches"
    )

    @api.depends("source_order_id.customer_id", "customer_id.partner_id")
    def _compute_source_customer_matches(self):
        for template in self:
            source = template.source_order_id.sudo()
            template.source_customer_matches = bool(
                source and source.customer_id == template.customer_id.sudo().partner_id
            )

    @api.model
    def _search_source_customer_matches(self, operator, value):
        if operator not in ("in", NOT_IN_OPERATOR):
            return NotImplemented
        # A live join also remains correct after the customer's merge updates foreign keys in SQL.
        self.flush_model(["source_order_id", "customer_id"])
        orders = self.env[MODEL_SALE_ORDER]
        customers = self.env[MODEL_CUSTOMER]
        orders.flush_model(["customer_id"])
        customers.flush_model(["partner_id"])
        matching = SQL(
            "SELECT t.id FROM %s t JOIN %s o ON o.id = t.source_order_id "
            "JOIN %s c ON c.id = t.customer_id WHERE o.customer_id = c.partner_id",
            SQL.identifier(self._table),
            SQL.identifier(orders._table),
            SQL.identifier(customers._table),
        )
        positive = (True in value) != (operator == NOT_IN_OPERATOR)
        return Domain("id", "in" if positive else NOT_IN_OPERATOR, matching)

    @api.model
    def _check_source(self, source):
        source.check_access("read")
        if not source.exists():
            raise AccessError(self.env._("The source order is not available."))
        broad = self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP)
        if not broad and source.user_id != self.env.user:
            raise AccessError(self.env._("Only the assigned salesperson can use this source order."))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        selections = []
        for vals in vals_list:
            commands = vals.pop("line_ids", []) or []
            if any(command[0] != Command.CREATE for command in commands):
                raise AccessError(self.env._("New templates can only contain new selections."))
            selections.append(commands)
            vals["line_ids"] = []
            source = self.env[MODEL_SALE_ORDER].browse(vals.get("source_order_id"))
            self._check_source(source)
            customer = source._customer_record()
            if not customer or not customer.active or vals.get("customer_id") != customer.id:
                raise ValidationError(self.env._("Choose an active customer belonging to the source order."))
            if not commands:
                raise ValidationError(self.env._("An order template needs at least one selection."))
            if not (vals.get("name") or "").strip():
                raise ValidationError(self.env._("Give the template a name."))
            vals["name"] = vals["name"].strip()
        with self.env.cr.savepoint():
            templates = super().create(vals_list)
            token = CREATING_TEMPLATE_IDS.set(frozenset(templates.ids))
            try:
                self.env[MODEL_ORDER_TEMPLATE_LINE].create(
                    [
                        {**command[2], "template_id": template.id}
                        for template, commands in zip(templates, selections, strict=True)
                        for command in commands
                    ]
                )
            finally:
                CREATING_TEMPLATE_IDS.reset(token)
            templates._check_has_selections()
            return templates

    def _check_has_selections(self):
        if any(not template.line_ids for template in self):
            raise ValidationError(self.env._("An order template needs at least one selection."))

    def write(self, vals):
        self.check_access("write")
        if {"customer_id", "source_order_id"} & vals.keys():
            raise AccessError(self.env._("The customer and source order of a template cannot be changed."))
        if "name" in vals:
            if not (vals["name"] or "").strip():
                raise ValidationError(self.env._("Give the template a name."))
            vals = {**vals, "name": vals["name"].strip()}
        if "line_ids" not in vals:
            return super().write(vals)
        # Child commands may temporarily empty a template while replacing its selections.
        with self.env.cr.savepoint():
            token = EDITING_TEMPLATE_IDS.set(EDITING_TEMPLATE_IDS.get() | frozenset(self.ids))
            try:
                result = super().write(vals)
            finally:
                EDITING_TEMPLATE_IDS.reset(token)
            self._check_has_selections()
            return result

    def _create_order(self):
        self.ensure_one()
        self.check_access("read")
        self._check_source(self.source_order_id)
        if self.source_order_id.sudo().customer_id != self.customer_id.sudo().partner_id:
            raise ValidationError(self.env._("The source order no longer belongs to the saved customer."))
        if not self.active or not self.customer_id.sudo().active:
            raise ValidationError(self.env._("An archived template or customer cannot be used to create an order."))
        commands, skipped = [], []
        for line in self.line_ids:
            reason = line._unavailability_reason()
            if reason:
                skipped.append(self.env._("%(item)s: %(reason)s", item=line.product_id.display_name, reason=reason))
            else:
                commands.append(line._order_line_command())
        if not commands:
            raise ValidationError(self.env._("No selections are available in the catalog.\n%s", "\n".join(skipped)))
        customer = self.customer_id.sudo()
        contact = customer.default_contact_id
        if not contact.active or contact.commercial_partner_id != customer.partner_id.commercial_partner_id:
            contact = customer.partner_id
        # The savepoint protects direct ORM callers that catch an unexpected construction error too.
        context = {key: value for key, value in self.env.context.items() if not key.startswith("default_")}
        with self.env.cr.savepoint():
            return (
                self.env[MODEL_SALE_ORDER]
                .with_context(context, medilab_sales_order=True)
                .create(
                    {
                        "customer_id": customer.partner_id.id,
                        "partner_id": contact.id,
                        "order_line": commands,
                        "template_omission_note": "\n".join(skipped),
                    }
                )
            )

    def action_create_order(self):
        order = self._create_order()
        return {"type": "ir.actions.act_window", "res_model": MODEL_SALE_ORDER, "res_id": order.id, "view_mode": "form"}
