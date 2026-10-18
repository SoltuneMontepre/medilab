from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_PRODUCT,
    MODEL_RECIPE,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED
from odoo.addons.sol_inventory.constants.xml_ids import PREPARATION_LOT_SEQUENCE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN, MODEL_PERSON


# Phiếu Pha Chế
class Preparation(models.Model):
    _name = MODEL_PREPARATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Preparation"
    _permission_actions = ("create",)

    # The recipe this preparation followed, one batch of it.
    recipe_id = fields.Many2one(MODEL_RECIPE, string="Recipe", required=True, ondelete="restrict")
    # The store the solution was prepared in and put back into.
    location_id = fields.Many2one(MODEL_STOCK_LOCATION, string="Store", required=True, ondelete="restrict")
    # The container the solution was put into.
    container_ids = fields.One2many(MODEL_STOCK_PACKAGE, "preparation_id", string="Container")
    # Moves of the ingredients, of any extra that was wasted, and of the solution put into the container.
    move_ids = fields.One2many(MODEL_STOCK_MOVE, "preparation_id", string="Moves")

    @api.depends("container_ids.name")
    def _compute_display_name(self):
        for preparation in self:
            preparation.display_name = preparation.container_ids[:1].name or preparation.recipe_id.display_name

    @api.model
    def prepare(self, recipe, location, ingredient_lines, received, scrap_tags):
        """Prepare one batch. ingredient_lines are dicts with item, quantity and containers in scan order. Each
        ingredient quantity is at least the recipe's; anything above it is wasted. received is at most the yield."""
        self._check_can_prepare()
        person = self.env[MODEL_PERSON]._for_user()
        if not location or location._holding_store() not in person._store():
            raise UserError(self.env._("Choose one of your stores."))
        self._check_batch(recipe, ingredient_lines, received, scrap_tags)
        preparation = self.create({"recipe_id": recipe.id, "location_id": location.id})
        moves = self.env[MODEL_STOCK_MOVE]
        production = moves._destination(recipe.solution_item_id, scrap=False)
        for ingredient in ingredient_lines:
            item = ingredient["item"]
            containers = ingredient["containers"]
            containers._check_for_use(person)
            outside = containers.filtered(lambda container: not container._is_in(location))
            if outside:
                raise UserError(
                    self.env._(
                        "%(containers)s are not in %(store)s.",
                        containers=format_list(self.env, outside.mapped("display_name")),
                        store=location.display_name,
                    )
                )
            recipe_quantity = recipe.line_ids.filtered(lambda line, item=item: line.item_id == item).quantity
            takes = moves._plan_containers(item, containers, ingredient["quantity"])
            recipe_takes, waste_takes = self._split_recipe(item, takes, recipe_quantity)
            moves |= moves._done_moves(item, recipe_takes, production, preparation_id=preparation.id)
            if waste_takes:
                scrap = moves._destination(item, scrap=True)
                moves |= moves._done_moves(
                    item,
                    waste_takes,
                    scrap,
                    scrap=True,
                    preparation_id=preparation.id,
                    scrap_reason_tag_ids=scrap_tags,
                )
        container = preparation._put_solution(received, moves, production)
        return preparation, container

    def _put_solution(self, received, ingredient_moves, production):
        """Put the solution into a new opened container and value that lot at the ingredients' cost."""
        self.ensure_one()
        solution = self.recipe_id.solution_item_id.sudo()
        if solution.tracking in ("lot", "serial") and not solution.use_expiration_date:
            solution.use_expiration_date = True
        if solution.tracking in ("lot", "serial") and not solution.lot_valuated:
            solution.lot_valuated = True
        spent = sum(abs(move.value) for move in ingredient_moves)
        unit = spent / received
        packages = self.env[MODEL_STOCK_PACKAGE]
        lot_name = self.env["ir.sequence"].next_by_code(PREPARATION_LOT_SEQUENCE)
        if not lot_name:
            raise UserError(self.env._("The prepared solution lot sequence is missing."))
        container = packages.sudo().create(
            {
                "name": packages._next_container_codes(lot_name, 1)[0],
                "status": CONTAINER_OPENED,
                "opened_at": fields.Datetime.now(),
                "opened_by_id": self.env.user.id,
                "preparation_id": self.id,
            }
        )
        lot = (
            self.env[MODEL_STOCK_LOT]
            .sudo()
            .create(
                {
                    "name": lot_name,
                    "product_id": solution.id,
                    "company_id": self.env.company.id,
                    "expiration_date": packages._at_utc(container.usable_until),
                }
            )
        )
        lot.standard_price = unit
        self.env[MODEL_STOCK_MOVE]._done_move(
            solution,
            production,
            self.location_id,
            [{"quantity": received, "lot": lot, "result_package": container}],
            preparation_id=self.id,
            price_unit=unit,
        )
        return container

    def _check_can_prepare(self):
        if self.env.su or "all" in self._user_scopes("create"):
            return
        raise AccessError(self.env._("You are not allowed to prepare a solution."))

    def _check_batch(self, recipe, ingredient_lines, received, scrap_tags):
        if not recipe or not recipe.active:
            raise UserError(self.env._("Choose a recipe."))
        solution_uom = recipe.uom_id
        if solution_uom.compare(received, 0) <= 0:
            raise UserError(self.env._("The quantity obtained must be above zero."))
        if solution_uom.compare(received, recipe.yield_quantity) > 0:
            raise UserError(
                self.env._(
                    "The quantity obtained cannot be more than the recipe yield of %(quantity)s %(unit)s.",
                    quantity=recipe.yield_quantity,
                    unit=solution_uom.name,
                )
            )
        items = recipe.line_ids.item_id
        given = self.env[MODEL_STOCK_PACKAGE].browse()
        seen = self.env[MODEL_PRODUCT].browse()
        extra = False
        for ingredient in ingredient_lines:
            item = ingredient["item"]
            if item not in items:
                raise UserError(self.env._("%s is not an ingredient of this recipe.", item.display_name))
            if item in seen:
                raise UserError(self.env._("%s is already on this preparation.", item.display_name))
            seen |= item
            recipe_quantity = recipe.line_ids.filtered(lambda line, item=item: line.item_id == item).quantity
            if item.uom_id.compare(ingredient["quantity"], recipe_quantity) < 0:
                raise UserError(self.env._("The amount of %s cannot be less than the recipe.", item.display_name))
            if item.uom_id.compare(ingredient["quantity"], recipe_quantity) > 0:
                extra = True
            wrong = ingredient["containers"].filtered(lambda container: container.item_id != item)
            if wrong:
                raise UserError(
                    self.env._(
                        "%(container)s holds %(held)s, not %(item)s.",
                        container=wrong[0].display_name,
                        held=wrong[0].item_id.display_name,
                        item=item.display_name,
                    )
                )
            for container in ingredient["containers"]:
                if container in given:
                    raise UserError(self.env._("%s is already used for another ingredient.", container.display_name))
                given |= container
        if seen != items:
            raise UserError(self.env._("Prepare every ingredient of %s.", recipe.display_name))
        if extra and not scrap_tags:
            raise UserError(self.env._("Give a reason for the extra ingredient."))

    @api.model
    def _split_recipe(self, item, takes, recipe_quantity):
        """The recipe's amount, then anything above it from the same containers."""
        recipe_takes = []
        waste_takes = []
        left = recipe_quantity
        for take in takes:
            if item.uom_id.compare(left, 0) <= 0:
                waste_takes.append(take)
                continue
            if item.uom_id.compare(take["quantity"], left) <= 0:
                recipe_takes.append(take)
                left = item.uom_id.round(left - take["quantity"])
                continue
            recipe_takes.append({**take, "quantity": left})
            waste_takes.append({**take, "quantity": item.uom_id.round(take["quantity"] - left)})
            left = 0.0
        return recipe_takes, waste_takes
