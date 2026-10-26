from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_inventory.constants.models import (
    MODEL_ANALYTIC_ACCOUNT,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_MOVE_LINE,
    MODEL_STOCK_PICKING,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import CANCELLED, DONE
from odoo.addons.sol_inventory.constants.xml_ids import COST_CENTRE_PLAN, STORE_VIEWS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_EMPLOYEE,
    MODEL_LOCATION,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP

# Fields that set up the stores; only administrators write them, the storekeeper maintains the other locations.
STORE_FIELDS = ("is_store", "holder_id", "manager_id")


# Vị Trí Kho
class StockLocation(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_LOCATION
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_LOCATION, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]

    # Storage conditions of the location, such as "2-8 °C".
    conditions = fields.Char(string="Storage Conditions")
    # True when the location is a store.
    is_store = fields.Boolean(string="Store", copy=False)
    # The department or team that holds the store; empty for the central store and for locations inside a store.
    holder_id = fields.Many2one(MODEL_DEPARTMENT, string="Holder", ondelete="restrict", copy=False)
    # The person who manages the store.
    manager_id = fields.Many2one(MODEL_EMPLOYEE, string="Manager", ondelete="restrict", copy=False)
    # The location of the company's premises the stock location is in, such as the room a store is in or the bench a
    # fridge stands on; empty while it is not placed.
    place_id = fields.Many2one(
        MODEL_LOCATION, string="Premises Location", ondelete="restrict", index="btree_not_null", copy=False
    )
    # The nearest store the location is inside; empty for the central store.
    parent_store_id = fields.Many2one(MODEL_STOCK_LOCATION, string="Store Above", compute="_compute_parent_store_id")
    # Code of the cost centre of the department or team that holds the store; empty while it has none.
    cost_centre_code = fields.Char(string="Cost Centre", compute="_compute_cost_centre")
    # True when a department or team holds the store but has no cost centre yet.
    cost_centre_missing = fields.Boolean(
        string="Without Cost Centre", compute="_compute_cost_centre", search="_search_cost_centre_missing"
    )

    @api.depends("location_id")
    def _compute_parent_store_id(self):
        for location in self:
            location.parent_store_id = location._store_above()

    @api.depends("holder_id")
    def _compute_cost_centre(self):
        codes = {centre.department_id.id: centre.code for centre in self._cost_centres(self.holder_id)}
        for location in self:
            location.cost_centre_code = codes.get(location.holder_id.id, False)
            location.cost_centre_missing = bool(location.holder_id) and not location.cost_centre_code

    def _search_cost_centre_missing(self, operator, value):
        if operator != "in" or True not in value:
            return NotImplemented
        holders = self._cost_centres().department_id
        return Domain("holder_id", "!=", False) & Domain("holder_id", "not in", holders.ids)

    def _cost_centres(self, departments=None):
        # Read with full rights: the Stores screen shows the cost centre to those who cannot open cost centres.
        domain = Domain("plan_id", "=", self.env.ref(COST_CENTRE_PLAN).id)
        if departments is not None:
            domain &= Domain("department_id", "in", departments.ids)
        return self.env[MODEL_ANALYTIC_ACCOUNT].sudo().search(domain)

    def unlink(self):
        # Odoo deletes the locations inside a location along with it; they are deleted or moved first. Odoo finds
        # them with a search that skips archived ones, so an archived location is deleted with archived ones included.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            inside = (
                self.sudo()
                .with_context(active_test=False)
                .search(Domain("location_id", "in", self.ids) & Domain("id", "not in", self.ids))
            )
            if inside:
                raise UserError(
                    self.env._(
                        "%(locations)s cannot be deleted while these locations are inside: %(inside)s.",
                        locations=format_list(self.env, inside.location_id.mapped("display_name")),
                        inside=format_list(self.env, inside.mapped("display_name")),
                    )
                )
        return super(StockLocation, self.with_context(active_test=False)).unlink()

    def _referrers_in_use(self, referrers):
        # Odoo's moves and transfers are finished once done or cancelled, and its quants hold stock only while their
        # quantity is not zero; finished ones keep their location but do not stop it being archived.
        if referrers._name in (MODEL_STOCK_MOVE, MODEL_STOCK_MOVE_LINE, MODEL_STOCK_PICKING):
            return ~Domain("state", "in", (DONE, CANCELLED))
        if referrers._name == MODEL_STOCK_QUANT:
            return Domain("quantity", "!=", 0)
        return super()._referrers_in_use(referrers)

    def _store_above(self):
        self.ensure_one()
        parent = self.location_id
        while parent and not parent.is_store:
            parent = parent.location_id
        return parent

    def _has_field_access(self, field, operation):
        if (
            field.name in STORE_FIELDS
            and operation == "write"
            and not self.env.su
            and not self.env.user.has_group(ADMINISTRATOR_GROUP)
        ):
            return False
        return super()._has_field_access(field, operation)

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id, view_type, **options)
        # The Stores screen creates stores, so it offers New only to those who set up the stores.
        if (
            view_id
            and view_id in [self.env["ir.model.data"]._xmlid_to_res_id(xml_id) for xml_id in STORE_VIEWS]
            and not self.has_field_access(self._fields["is_store"], "write")
        ):
            root = etree.fromstring(result["arch"])
            root.set("create", "False")
            result["arch"] = etree.tostring(root, encoding="unicode")
        return result

    @api.constrains("is_store", "location_id", "holder_id", "active")
    def _check_store_tree(self):
        # A change to a location also moves or re-holds the stores inside it.
        locations = self.sudo()
        stores = locations.search(Domain("id", "child_of", self.ids) & Domain("is_store", "=", True))
        # Locations with no store in or under them leave the tree of stores unchanged.
        if not stores and not self.filtered("is_store"):
            return
        for store in stores:
            store._check_holder()
        central = self._central_stores()
        if len(central) > 1:
            raise ValidationError(
                self.env._(
                    "Only the central store has no store above it, but these stores have none: %s.",
                    format_list(self.env, central.mapped("display_name")),
                )
            )

    def _central_stores(self):
        """The stores with no store above them: the central store once the stores are set up."""
        return self.sudo().search(Domain("is_store", "=", True)).filtered(lambda store: not store._store_above())

    def _check_in_central_store(self):
        """Refuse receiving goods into a location outside the central store, listing those locations."""
        if not self:
            return
        central = self._central_stores()[:1]
        if not central:
            raise ValidationError(self.env._("Set up the central store before receiving goods."))
        # A location inside a store below the central store belongs to that store.
        outside = self.filtered(
            lambda location: (location if location.is_store else location.sudo().parent_store_id) != central
        )
        if outside:
            raise ValidationError(
                self.env._(
                    "Goods can be received only into a location of the central store %(store)s, not into: %(locations)s.",
                    store=central.display_name,
                    locations=format_list(self.env, outside.sudo().mapped("display_name")),
                )
            )

    def _check_holder(self):
        above = self._store_above()
        if not above:
            if self.holder_id:
                raise ValidationError(
                    self.env._("%s is the central store, so no department or team holds it.", self.display_name)
                )
            return
        if not self.holder_id:
            raise ValidationError(
                self.env._(
                    "%(store)s is below %(above)s, so a department or team must hold it.",
                    store=self.display_name,
                    above=above.display_name,
                )
            )
        department = self.holder_id.parent_id
        if department and above.holder_id != department:
            raise ValidationError(
                self.env._(
                    "%(store)s is held by the team %(team)s, so the store above it must be held by %(department)s.",
                    store=self.display_name,
                    team=self.holder_id.name,
                    department=department.name,
                )
            )

    def _check_receives_requisitions(self):
        """Refuse a requisition to a store that names no manager to approve and issue it."""
        unmanaged = self.filtered(lambda store: not store.manager_id)
        if unmanaged:
            raise UserError(
                self.env._(
                    "These stores have no manager, so they cannot receive requisitions: %s.",
                    format_list(self.env, unmanaged.mapped("display_name")),
                )
            )
