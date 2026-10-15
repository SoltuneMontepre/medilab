from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_METHOD_CONSUMPTION,
    MODEL_PRODUCT,
    MODEL_STOCK_QUANT,
    MODEL_SUPPLIER_INFO,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_CHEMICAL, MODEL_PERMISSION_MIXIN

STOCK_ITEM_SEQUENCE = "medilab.stock.item"
PRODUCT_MANAGER_GROUP = "product.group_product_manager"
CHEMICAL = "chemical"
CONTAINER = "container"
LOT = "lot"
QUANTITY = "quantity"
# The parts of an item edited on its form, which their own permissions govern.
PART_FIELDS = ("orderpoint_ids", "supplier_item_ids", "consumption_ids")
# Fields that change how an item's stock is counted.
TRACKING_FIELDS = ("tracking", "track_containers", "item_tracking", "is_storable")


# Vật Tư
class ProductProduct(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_PRODUCT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PRODUCT, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "archive")
    _audit_children = PART_FIELDS
    # An item's permissions govern its template too, which Odoo lets only product managers change.
    _check_inherits_access = False

    # Unique code of the product; filled from a sequence for a stock item left without one.
    default_code = fields.Char(copy=False)
    # chemical, consumable, spare_part or solution; empty for a product that is not a stock item.
    item_kind = fields.Selection(
        [
            (CHEMICAL, "Chemical or Reagent"),
            ("consumable", "Consumable"),
            ("spare_part", "Spare Part"),
            ("solution", "Prepared Solution"),
        ],
        string="Item Kind",
        index=True,
    )
    # True when each bottle or vial of the item is a container with its own code.
    track_containers = fields.Boolean(string="Track Containers", copy=False)
    # How the item is counted: by container, by lot or by quantity only; sets Odoo's tracking and track_containers.
    item_tracking = fields.Selection(
        [(CONTAINER, "By Container"), (LOT, "By Lot"), (QUANTITY, "By Quantity")],
        string="Item Tracking",
        compute="_compute_item_tracking",
        inverse="_inverse_item_tracking",
    )
    # The Laboratory chemical the item stocks; set only for a chemical.
    chemical_id = fields.Many2one(MODEL_CHEMICAL, string="Chemical", ondelete="restrict", copy=False)
    # Days an opened container stays usable; 0 when opening does not shorten its life.
    shelf_life_after_opening_days = fields.Integer(string="Shelf Life After Opening (Days)")
    # The vendor prices of the item, one per supplier.
    supplier_item_ids = fields.One2many(MODEL_SUPPLIER_INFO, "product_id", string="Suppliers")
    # How much of the item one test of each method uses.
    consumption_ids = fields.One2many(MODEL_METHOD_CONSUMPTION, "product_id", string="Use per Test")

    _default_code_unique = models.Constraint("UNIQUE(default_code)", "Another product already has this code.")
    _chemical_unique = models.Constraint("UNIQUE(chemical_id)", "Another item already stocks this chemical.")
    _shelf_life_not_negative = models.Constraint(
        "CHECK(shelf_life_after_opening_days >= 0)", "The shelf life after opening cannot be negative."
    )

    @api.depends("tracking", "track_containers")
    def _compute_item_tracking(self):
        for item in self:
            if item.tracking == LOT:
                item.item_tracking = CONTAINER if item.track_containers else LOT
            else:
                item.item_tracking = QUANTITY

    def _inverse_item_tracking(self):
        for item in self:
            item.write(self._tracking_values(item.item_tracking))

    @api.model
    def _tracking_values(self, item_tracking):
        """Odoo's tracking and track_containers for the way the storekeeper counts an item."""
        item_tracking = item_tracking or QUANTITY
        return {"tracking": item_tracking != QUANTITY and LOT, "track_containers": item_tracking == CONTAINER}

    @api.constrains("item_kind", "chemical_id", "tracking", "track_containers")
    def _check_chemical(self):
        for item in self.filtered("item_kind"):
            if item.item_kind != CHEMICAL:
                if item.chemical_id:
                    raise ValidationError(
                        self.env._("%s is not a chemical, so it stocks no Laboratory chemical.", item.display_name)
                    )
                continue
            if not item.chemical_id:
                raise ValidationError(
                    self.env._("%s is a chemical, so it stocks one Laboratory chemical.", item.display_name)
                )
            if item.item_tracking != CONTAINER:
                raise ValidationError(self.env._("%s is a chemical, so it is tracked by container.", item.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Set before the constraints run, which an inverse is not.
            if "item_tracking" in vals:
                vals.update(self._tracking_values(vals.pop("item_tracking")))
            if vals.get("item_kind"):
                vals.setdefault("is_storable", True)
                if not vals.get("default_code"):
                    vals["default_code"] = self.env["ir.sequence"].next_by_code(STOCK_ITEM_SEQUENCE)
        if self.env.su or not all(vals.get("item_kind") for vals in vals_list):
            self._check_product_manager()
            return super().create(vals_list)
        self.check_access("create")
        self._check_field_rights({name for vals in vals_list for name in vals})
        return super(ProductProduct, self.sudo()).create(vals_list).with_env(self.env)

    def write(self, vals):
        if "item_tracking" in vals:
            vals = {**vals, **self._tracking_values(vals["item_tracking"])}
            del vals["item_tracking"]
        items = self._as_items()
        if items is None:
            self._check_product_manager()
        else:
            items._check_item_rights(vals)
        if "active" in vals and not vals["active"]:
            self.filtered("item_kind")._check_archivable()
        tracking_before = self._item_trackings() if set(TRACKING_FIELDS) & vals.keys() else None
        if items is None:
            result = super().write(vals)
        else:
            # The item's own fields and its template's are written with full rights; its parts are written as the
            # user, so their own permissions apply.
            own = {name: value for name, value in vals.items() if name not in PART_FIELDS}
            parts = {name: value for name, value in vals.items() if name in PART_FIELDS}
            if own:
                super(ProductProduct, items.sudo()).write(own)
            if parts:
                super().write(parts)
            result = True
        if tracking_before:
            self.filtered(lambda item: item.id in tracking_before)._check_tracking_kept(tracking_before)
        return result

    def action_archive(self):
        # Odoo archives an item through its template, which only product managers may change.
        items = self._as_items()
        if items is None:
            return super().action_archive()
        items._check_item_rights({"active": False})
        return super(ProductProduct, items.sudo()).action_archive()

    def action_unarchive(self):
        items = self._as_items()
        if items is None:
            return super().action_unarchive()
        items._check_item_rights({"active": True})
        return super(ProductProduct, items.sudo()).action_unarchive()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_stock_item(self):
        # Odoo lets its product managers delete products; stock items stay, archived, for the records that name them.
        if self.filtered("item_kind"):
            raise UserError(self.env._("Stock items are archived, never deleted."))

    def _as_items(self):
        """The records when they are all stock items handled for a user; None when Odoo's own rights apply."""
        if self.env.su or not self or not all(self.mapped("item_kind")):
            return None
        return self

    def _check_item_rights(self, vals):
        """Check the item permissions the change needs, before it is made with full rights."""
        self.check_access("write")
        if "active" in vals:
            self._check_permission("archive")
        if set(vals) - {"active"} - set(PART_FIELDS):
            self._check_permission("edit")
        self._check_field_rights(set(vals) - set(PART_FIELDS))

    def _check_field_rights(self, names):
        for name in names & self._fields.keys():
            self.check_field_access(self._fields[name], "write")

    def _check_product_manager(self):
        # The item permissions give accesses on every product; other products stay with Odoo's product managers.
        if not self.env.su and not self.env.user.has_group(PRODUCT_MANAGER_GROUP):
            raise AccessError(self.env._("Only product managers may change products that are not stock items."))

    def _check_archivable(self):
        """Refuse archiving items held in stock or used per test by an active testing method, listing what holds them."""
        quants = self._held_stock()
        if quants:
            raise UserError(
                self.env._(
                    "%(items)s cannot be archived while stock is held in: %(locations)s.",
                    **self._stock_names(quants),
                )
            )
        uses = (
            self.env[MODEL_METHOD_CONSUMPTION]
            .sudo()
            .search(Domain("product_id", "in", self.ids) & Domain("method_id.active", "=", True))
        )
        if uses:
            raise UserError(
                self.env._(
                    "%(items)s cannot be archived while used per test by: %(methods)s.",
                    items=format_list(self.env, uses.product_id.mapped("display_name")),
                    methods=format_list(self.env, uses.method_id.mapped("display_name")),
                )
            )

    def _item_trackings(self):
        return {item.id: item.item_tracking for item in self.filtered("item_kind")}

    def _check_tracking_kept(self, tracking_before):
        """Refuse a new tracking for items with stock on hand, listing the locations that hold it."""
        changed = self.filtered(lambda item: item.item_tracking != tracking_before[item.id])
        quants = changed._held_stock()
        if quants:
            raise UserError(
                self.env._(
                    "The tracking of %(items)s cannot change while stock is held in: %(locations)s.",
                    **self._stock_names(quants),
                )
            )

    def _stock_names(self, quants):
        return {
            "items": format_list(self.env, quants.product_id.mapped("display_name")),
            "locations": format_list(self.env, quants.location_id.mapped("display_name")),
        }

    def _held_stock(self):
        """The quants of the items' stock on hand in the laboratory's own locations."""
        if not self:
            return self.env[MODEL_STOCK_QUANT]
        return (
            self.env[MODEL_STOCK_QUANT]
            .sudo()
            .search(
                Domain("product_id", "in", self.ids)
                & Domain("location_id.usage", "=", "internal")
                & Domain("quantity", "!=", 0)
            )
        )
