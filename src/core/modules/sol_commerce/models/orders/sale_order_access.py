from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP

HIDDEN = ("1", "True")
ALL_RECORDS = "[(1, '=', 1)]"
FOLLOWS_ORDER_READ = "[('order_id', 'access', 'read')]"
FOLLOWS_ORDER_WRITE = "[('order_id', 'access', 'write')]"
# Domains of the generated order accesses. Read all and edit all cover every order, and read own adds the unclaimed
# queue a salesperson claims from. Samples, quotations and cancellation requests follow what the user may do on their
# order.
PERMISSION_ACCESS_DOMAINS = {
    "order_read_all": ALL_RECORDS,
    "order_edit_all": ALL_RECORDS,
    "order_read_own": (
        "['|', ('user_id', '=', user.id), '&', ('order_status', '=', 'submitted'), ('user_id', '=', False)]"
    ),
    "cancellation_request_read_all": FOLLOWS_ORDER_READ,
    "cancellation_request_edit_all": FOLLOWS_ORDER_WRITE,
    "order_sample_read_all": FOLLOWS_ORDER_READ,
    "order_sample_edit_all": FOLLOWS_ORDER_WRITE,
    "order_sample_delete_all": FOLLOWS_ORDER_WRITE,
    "quotation_read_all": FOLLOWS_ORDER_READ,
    "quotation_edit_all": FOLLOWS_ORDER_WRITE,
    "quotation_delete_all": FOLLOWS_ORDER_WRITE,
}
# Header actions that stay on an order the user may only read: claiming the unclaimed order makes it theirs.
READER_ACTIONS = ("action_claim",)


# Đơn Hàng: a salesperson who may read another salesperson's order opens it read-only.
class SaleOrder(models.Model):
    _inherit = MODEL_SALE_ORDER

    # True when the current user may change the order: they own it, edit every order or see all orders.
    order_can_edit = fields.Boolean(compute="_compute_order_can_edit")

    @api.depends("user_id")
    @api.depends_context("uid")
    def _compute_order_can_edit(self):
        for order in self:
            order.order_can_edit = order._can_edit()

    def _can_edit(self):
        self.ensure_one()
        if not self._origin.id:
            # A new order is the user's own; creating it is checked by its own permission.
            return True
        scopes = self._user_scopes("edit")
        return self.env.su or "all" in scopes or ("own" in scopes and self.user_id == self.env.user)

    def _user_scopes(self, action):
        """The Head of Sales acts on every order with the permissions they hold, whatever their scope."""
        scopes = super()._user_scopes(action)
        if scopes and self.env.user.has_group(ALL_ORDERS_GROUP):
            return {"all"}
        return scopes

    @api.model
    def _scope_permission_accesses(self):
        """Set the domains of the generated order accesses, which Odoo does not update on upgrade."""
        for code, domain in PERMISSION_ACCESS_DOMAINS.items():
            self.env.ref(f"sol_laboratory.access_permission_{code}").sudo().domain = domain

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        """Make the order form read-only, and hide its actions but Claim, on an order the user may not change."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type != "form":
            return arch, view
        for node in arch.xpath("//sheet//field[not(ancestor::field)]"):
            node.set("readonly", self._or_locked(node.get("readonly")))
        for node in arch.xpath("//header/button"):
            if node.get("name") not in READER_ACTIONS:
                node.set("invisible", self._or_locked(node.get("invisible")))
        sheet = arch.find(".//sheet")
        if sheet is not None:
            sheet.insert(0, arch.makeelement("field", {"name": "order_can_edit", "invisible": "1"}))
        return arch, view

    @staticmethod
    def _or_locked(condition):
        if condition in HIDDEN:
            return condition
        return f"({condition}) or not order_can_edit" if condition else "not order_can_edit"
