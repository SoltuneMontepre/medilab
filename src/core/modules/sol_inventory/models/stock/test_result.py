from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_METHOD_CONSUMPTION,
    MODEL_RESULT_CONTAINER,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TEST_RESULT


# Kết Quả Thử Nghiệm
class TestResult(models.Model):
    _inherit = MODEL_TEST_RESULT
    _audit_children = ("container_line_ids",)

    # Containers scanned for this result, in the order they are used up. A new version does not copy them.
    container_line_ids = fields.One2many(MODEL_RESULT_CONTAINER, "result_id", string="Containers", copy=False)
    # Code read from a container's label; it adds the container and is not stored.
    container_scan = fields.Char(string="Scan Container", store=False)
    # Moves recorded when this result was first signed.
    move_ids = fields.One2many(MODEL_STOCK_MOVE, "test_result_id", string="Moves", copy=False)

    @api.onchange("container_scan")
    def _onchange_container_scan(self):
        code = (self.container_scan or "").strip()
        if not code:
            return
        container = self.env[MODEL_STOCK_PACKAGE]._find_by_code(code)
        if container in self.container_line_ids.container_id:
            raise UserError(self.env._("%s is already on this result.", container.display_name))
        sequence = max(self.container_line_ids.mapped("sequence") or [0]) + 1
        self.container_line_ids = [Command.create({"container_id": container.id, "sequence": sequence})]
        self.container_scan = False

    def write(self, vals):
        if "container_line_ids" in vals and any(result.status != STATE_NONE for result in self):
            raise UserError(self.env._("The containers of a signed result stay as they were."))
        return super().write(vals)

    def action_sign(self):
        self.ensure_one()
        # The first signature of an in-house result deducts the method's usual use. A later signature, an outsourced
        # result and a new version of a result do not.
        if self.status == STATE_NONE and not self.replaces_id and not self.subcontractor_id:
            self._deduct_usual_use()
        return super().action_sign()

    def _deduct_usual_use(self):
        """Deduct the testing method's usual use from the store of the person who entered the result."""
        self.ensure_one()
        way = self._way_of_testing()
        if not way or not way.method_id:
            return None
        consumptions = self.env[MODEL_METHOD_CONSUMPTION].sudo().search([("method_id", "=", way.method_id.id)])
        if not consumptions:
            return None
        person = self.env[MODEL_PERSON]._for_user(self.entered_by_id)
        scanned = self.container_line_ids.container_id
        wrong = scanned.filtered(lambda container: container.item_id not in consumptions.product_id)
        if wrong:
            raise UserError(
                self.env._(
                    "%(containers)s hold %(items)s, which this method does not use.",
                    containers=format_list(self.env, wrong.mapped("display_name")),
                    items=format_list(self.env, wrong.item_id.mapped("display_name")),
                )
            )
        moves = self.env[MODEL_STOCK_MOVE]
        # Bottles first, so a missing scan refuses before any lot is taken.
        for consumption in consumptions.sorted(key=lambda consumption: not consumption.product_id.track_containers):
            item = consumption.product_id
            if item.track_containers:
                containers = scanned.filtered(lambda container, item=item: container.item_id == item)
                if not containers:
                    raise UserError(self.env._("Scan an opened container of %s.", item.display_name))
                moves |= moves._take_containers(
                    item,
                    containers,
                    consumption.quantity,
                    person=person,
                    automatic=True,
                    test_result_id=self.id,
                )
            else:
                moves |= moves._take_quants(
                    item,
                    person._store(),
                    consumption.quantity,
                    automatic=True,
                    test_result_id=self.id,
                )
        return moves
