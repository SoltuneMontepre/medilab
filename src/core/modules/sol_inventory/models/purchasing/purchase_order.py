from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER
from odoo.addons.sol_inventory.constants.stock import ORDER_DRAFT, ORDER_SENT, RECEIVED
from odoo.addons.sol_laboratory.constants.approvals import STATE_APPROVED, STATE_NONE, STATE_REJECTED, STATE_REQUESTED
from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERMISSION_MIXIN


# Đơn Mua Hàng
class PurchaseOrder(models.Model):
    _name = MODEL_PURCHASE_ORDER
    _inherit = [MODEL_PURCHASE_ORDER, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("read", "create", "edit", "delete", "sign")

    # draft while the order is prepared and signed, purchase once it is sent to the supplier, which confirms it, or
    # cancel; MediLab has no quotation request, so the labels follow its own steps.
    state = fields.Selection(selection_add=[(ORDER_DRAFT, "Draft"), (ORDER_SENT, "Sent")])
    # The department that asked for the stock.
    department_id = fields.Many2one(
        MODEL_DEPARTMENT, string="Department", domain=DEPARTMENT_DOMAIN, ondelete="restrict", index="btree_not_null"
    )
    # none, requested, approved or rejected: where the order stands in its approval chain, kept in step with its
    # signatures.
    approval_status = fields.Selection(
        [
            (STATE_NONE, "Not requested"),
            (STATE_REQUESTED, "Waiting for signature"),
            (STATE_APPROVED, "Signed"),
            (STATE_REJECTED, "Rejected"),
        ],
        string="Approval",
        required=True,
        default=STATE_NONE,
        copy=False,
    )

    _partner_state_idx = models.Index("(partner_id, state)")

    @api.constrains("partner_id")
    def _check_supplier(self):
        # An archived supplier keeps its contact for the orders that name it, but new orders do not go to it.
        for order in self:
            if not order.partner_id.sudo().supplier_ids:
                raise ValidationError(
                    self.env._("%s is not an active supplier, so it cannot be ordered from.", order.partner_id.name)
                )

    @api.model
    def _in_use_domain(self):
        # An order is finished once it is cancelled or everything it ordered has arrived.
        return Domain("state", "=", ORDER_DRAFT) | (
            Domain("state", "=", ORDER_SENT) & Domain("receipt_status", "!=", RECEIVED)
        )

    def _approval_allowed(self):
        # The approval chain signs every order before it is sent, so Odoo's own approval of large orders is off.
        return True
