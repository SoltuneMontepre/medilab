from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_PREPARATION_MAKE,
    MODEL_PREPARATION_MAKE_LINE,
    MODEL_RECIPE,
    MODEL_SCRAP_REASON_TAG,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON


# Pha Dung Dịch
class PreparationMake(models.TransientModel):
    _name = MODEL_PREPARATION_MAKE
    _description = "Prepare Solution"

    # The recipe of the one batch being prepared.
    recipe_id = fields.Many2one(MODEL_RECIPE, string="Recipe", required=True, domain=[("active", "=", True)])
    # The store the ingredients are in and the solution is put back into.
    location_id = fields.Many2one(
        MODEL_STOCK_LOCATION, string="Store", required=True, domain="[('id', 'in', store_ids)]"
    )
    # Stores the signed-in person prepares in.
    store_ids = fields.Many2many(MODEL_STOCK_LOCATION, string="Stores", compute="_compute_store_ids")
    # Code read from a container's label; it adds the container to the line of its ingredient and is not stored.
    container_scan = fields.Char(string="Scan Container", store=False)
    # One line per ingredient.
    line_ids = fields.One2many(MODEL_PREPARATION_MAKE_LINE, "wizard_id", string="Ingredients")
    # Quantity of solution obtained, in the solution's unit. Defaults to the yield and can only be lowered.
    received_quantity = fields.Float(string="Quantity Obtained", digits="Product Unit")
    # The unit of the quantity obtained: the solution's.
    uom_id = fields.Many2one(related="recipe_id.uom_id")
    # Why the extra ingredient was wasted. Required when an ingredient amount is above the recipe.
    scrap_reason_tag_ids = fields.Many2many(MODEL_SCRAP_REASON_TAG, string="Reason for the Extra")
    # True when an ingredient amount is above the recipe.
    has_extra = fields.Boolean(compute="_compute_has_extra")

    @api.depends("line_ids.quantity", "line_ids.recipe_quantity", "line_ids.item_id")
    def _compute_has_extra(self):
        for wizard in self:
            wizard.has_extra = any(
                line.item_id and line.item_id.uom_id.compare(line.quantity, line.recipe_quantity) > 0
                for line in wizard.line_ids
            )

    @api.depends_context("uid")
    def _compute_store_ids(self):
        stores = self.env[MODEL_PERSON]._for_user()._store()
        for wizard in self:
            wizard.store_ids = stores

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        stores = self.env[MODEL_PERSON]._for_user()._store()
        if "location_id" in fields_list and len(stores) == 1:
            defaults["location_id"] = stores.id
        return defaults

    @api.onchange("recipe_id")
    def _onchange_recipe_id(self):
        recipe = self.recipe_id
        self.received_quantity = recipe.yield_quantity
        self.line_ids = [Command.clear()]
        self.line_ids = [
            Command.create({"item_id": line.item_id.id, "recipe_quantity": line.quantity, "quantity": line.quantity})
            for line in recipe.line_ids
        ]

    @api.onchange("container_scan")
    def _onchange_container_scan(self):
        """A scanned container joins the line of the ingredient it holds, after the ones scanned before it."""
        code = (self.container_scan or "").strip()
        if not code:
            return
        container = self.env[MODEL_STOCK_PACKAGE]._find_by_code(code)
        if container in self.line_ids.container_ids.container_id:
            raise UserError(self.env._("%s is already on this preparation.", container.display_name))
        line = self.line_ids.filtered(lambda line: line.item_id == container.item_id)
        if not line:
            raise UserError(
                self.env._(
                    "%(container)s holds %(item)s, which this recipe does not use.",
                    container=container.display_name,
                    item=container.item_id.display_name,
                )
            )
        line._add_container(container)
        self.container_scan = False

    def action_prepare(self):
        """Prepare one batch and print the label of the container it fills."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("Choose a recipe."))
        _preparation, container = self.env[MODEL_PREPARATION].prepare(
            self.recipe_id,
            self.location_id,
            [
                {"item": line.item_id, "quantity": line.quantity, "containers": line.container_ids.container_id}
                for line in self.line_ids
            ],
            self.received_quantity,
            self.scrap_reason_tag_ids,
        )
        return self.env.ref(CONTAINER_LABEL_REPORT).report_action(container)
