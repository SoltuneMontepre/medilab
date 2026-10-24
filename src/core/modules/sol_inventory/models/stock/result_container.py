from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_RESULT_CONTAINER, MODEL_STOCK_PACKAGE
from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_TEST_RESULT


# Chai đã quét cho một kết quả thử nghiệm.
class ResultContainer(models.Model):
    _name = MODEL_RESULT_CONTAINER
    _inherit = [MODEL_AUDIT_MIXIN]
    _description = "Result Container"
    _order = "sequence, id"

    # The result the container was scanned for.
    result_id = fields.Many2one(MODEL_TEST_RESULT, required=True, ondelete="cascade", index=True)
    # The container that was scanned.
    container_id = fields.Many2one(
        MODEL_STOCK_PACKAGE, string="Container", required=True, ondelete="restrict", index=True
    )
    # Place in the scan order. Earlier containers are used up first.
    sequence = fields.Integer(default=10)
    # The item in the container.
    item_id = fields.Many2one(MODEL_PRODUCT, related="container_id.item_id")
    # Quantity left in the container, in its item's unit.
    quantity = fields.Float(related="container_id.quantity", digits="Product Unit")

    _result_container_unique = models.Constraint(
        "UNIQUE(result_id, container_id)", "This container is already on the result."
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_open()
        return lines

    def write(self, vals):
        self._check_open()
        return super().write(vals)

    def unlink(self):
        self._check_open()
        return super().unlink()

    def _check_open(self):
        """Only a draft result that the user may edit takes a change to its scanned containers."""
        if self.env.su:
            return
        locked = self.result_id.filtered(lambda result: result.status != STATE_NONE)
        if locked:
            raise UserError(self.env._("The containers of a signed result stay as they were."))
        self.result_id._check_permission("edit")
