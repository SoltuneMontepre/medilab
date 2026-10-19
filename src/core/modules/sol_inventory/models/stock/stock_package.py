import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list
from odoo.tools.sql import escape_like_value

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_PRODUCT,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_MOVE_LINE,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
    CONTAINER_MISSING,
    CONTAINER_OPENED,
    CONTAINER_SEALED,
    DONE,
    IN_STOCK_STATUSES,
    LOT_AVAILABLE,
)
from odoo.addons.sol_inventory.constants.xml_ids import (
    CONTAINER_ACTION,
    CONTAINER_LABEL_REPORT,
    SMALL_CONTAINER_LABEL_REPORT,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_RES_USERS,
)

MARKED_EMPTY = "Marked empty"


# Chai/Lọ
class StockPackage(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_PACKAGE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_PACKAGE, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _permission_actions = ("edit",)

    # sealed, opened, depleted, disposed or missing.
    status = fields.Selection(
        [
            (CONTAINER_SEALED, "Sealed"),
            (CONTAINER_OPENED, "Opened"),
            (CONTAINER_DEPLETED, "Depleted"),
            (CONTAINER_DISPOSED, "Disposed"),
            (CONTAINER_MISSING, "Missing"),
        ],
        required=True,
        default=CONTAINER_SEALED,
    )
    # When the container was opened or the solution in it was prepared.
    opened_at = fields.Datetime(string="Opened At", copy=False)
    # The day the container was opened or prepared, in the laboratory's time zone, for its label.
    opened_on = fields.Date(string="Opened On", compute="_compute_opened_on")
    # Who opened the container or prepared the solution in it.
    opened_by_id = fields.Many2one(MODEL_RES_USERS, string="Opened By", copy=False, ondelete="restrict")
    # The preparation that filled this container; empty for a container that was received.
    preparation_id = fields.Many2one(MODEL_PREPARATION, string="Preparation", copy=False, ondelete="restrict")
    # Last day the container can be used. Empty when its lot has no expiry and it is still sealed.
    usable_until = fields.Date(string="Usable Until", compute="_compute_usable_until", store=True)
    # The item in the container. Kept after the stock is gone, because Odoo deletes a quant at zero.
    item_id = fields.Many2one(MODEL_PRODUCT, string="Item", compute="_compute_content", store=True, ondelete="restrict")
    # The lot of the stock in the container. Kept after the stock is gone.
    lot_id = fields.Many2one(MODEL_STOCK_LOT, string="Lot", compute="_compute_content", store=True, ondelete="restrict")
    # Quantity left in the container, in its item's unit.
    quantity = fields.Float(string="Quantity Left", digits="Product Unit", compute="_compute_quantity")
    # Done move lines that took stock from the container or put stock into it.
    done_line_ids = fields.Many2many(MODEL_STOCK_MOVE_LINE, string="Moves", compute="_compute_done_line_ids")

    _name_unique = models.Constraint("UNIQUE(name)", "Another container already has this code.")
    _preparation_unique = models.Constraint("UNIQUE(preparation_id)", "A preparation fills one container.")
    _location_status_idx = models.Index("(location_id, status)")
    _status_usable_idx = models.Index("(status, usable_until)")

    @api.depends("quant_ids.product_id", "quant_ids.lot_id", "quant_ids.quantity")
    def _compute_content(self):
        for container in self:
            quants = container.sudo().quant_ids.filtered(lambda quant: quant.quantity > 0)
            if quants:
                container.item_id = quants.product_id[:1]
                container.lot_id = quants.lot_id[:1]
            else:
                # A quant at zero is deleted, and the container still is the item and lot it held.
                container.item_id = container._origin.item_id
                container.lot_id = container._origin.lot_id

    @api.depends("quant_ids.quantity")
    def _compute_quantity(self):
        for container in self:
            container.quantity = sum(container.sudo().quant_ids.mapped("quantity"))

    @api.depends("opened_at")
    def _compute_opened_on(self):
        for container in self:
            container.opened_on = self._as_date(container.opened_at)

    @api.depends("status", "opened_at", "lot_id.expiration_date", "item_id.shelf_life_after_opening_days")
    def _compute_usable_until(self):
        for container in self:
            container.usable_until = container._usable_date()

    def _compute_done_line_ids(self):
        lines = (
            self.env[MODEL_STOCK_MOVE_LINE]
            .sudo()
            .search(
                [
                    ("state", "=", DONE),
                    "|",
                    ("package_id", "in", self.ids),
                    ("result_package_id", "in", self.ids),
                ]
            )
        )
        for container in self:
            container.done_line_ids = lines.filtered(
                lambda line, container=container: container in (line.package_id, line.result_package_id)
            )

    def _usable_date(self):
        """Last day this container can be used: its lot's expiry, and once opened also its opening day plus the
        item's shelf life after opening, when that shelf life is above 0. A solution's lot expires on the date its
        preparation worked out. No date means the lot prints no expiry."""
        self.ensure_one()
        lot_date = self._as_date(self.lot_id.expiration_date)
        opened_on = self._as_date(self.opened_at)
        shelf_life = self.item_id.shelf_life_after_opening_days
        if self.status == CONTAINER_SEALED or not opened_on or not shelf_life:
            return lot_date
        opened_until = opened_on + timedelta(days=shelf_life)
        return min(lot_date, opened_until) if lot_date else opened_until

    @api.model
    def _today(self):
        return fields.Date.context_today(self.with_context(tz=self.env.company.tz or "UTC"))

    @api.model
    def _as_date(self, moment):
        if not moment:
            return False
        laboratory = self.with_context(tz=self.env.company.tz or "UTC")
        return fields.Datetime.context_timestamp(laboratory, moment).date()

    @api.model
    def _at_utc(self, day):
        """Midnight of this day in the laboratory, as the naive UTC time Odoo stores."""
        if not day:
            return False
        zone = ZoneInfo(self.env.company.tz or "UTC")
        local = datetime.combine(day, time.min, tzinfo=zone)
        return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    def _action_open(self):
        """The Containers screen, listing these containers."""
        action = self.env["ir.actions.actions"]._for_xml_id(CONTAINER_ACTION)
        action["domain"] = [("id", "in", self.ids)]
        return action

    def action_open(self):
        """Open a sealed container that is still usable and in the signed-in person's store, and print its label."""
        self.ensure_one()
        self._check_permission("edit")
        if self.status != CONTAINER_SEALED:
            raise UserError(self.env._("%s is not sealed.", self.display_name))
        self._check_usable()
        person = self.env[MODEL_PERSON]._for_user()
        self._check_in_store(person)
        self.write({"status": CONTAINER_OPENED, "opened_at": fields.Datetime.now(), "opened_by_id": self.env.user.id})
        return self.action_print_label()

    def action_mark_empty(self):
        """Use up whatever is left in an opened container and mark it depleted. The move says Marked empty."""
        self.ensure_one()
        self._check_permission("edit")
        if self.status != CONTAINER_OPENED:
            raise UserError(self.env._("Only an opened container is marked empty: %s.", self.display_name))
        person = self.env[MODEL_PERSON]._for_user()
        self._check_in_store(person)
        if self.item_id and not self.item_id.uom_id.is_zero(self.quantity):
            self.env[MODEL_STOCK_MOVE]._take_containers(
                self.item_id,
                self,
                self.quantity,
                check_use=False,
                automatic=False,
                reason=MARKED_EMPTY,
                reference=MARKED_EMPTY,
            )
        else:
            self.status = CONTAINER_DEPLETED
        return True

    def action_print_label(self):
        self.ensure_one()
        return self.env.ref(CONTAINER_LABEL_REPORT).report_action(self)

    def action_print_label_small(self):
        self.ensure_one()
        return self.env.ref(SMALL_CONTAINER_LABEL_REPORT).report_action(self)

    @api.model
    def _find_by_code(self, code):
        code = (code or "").strip()
        container = self.search([("name", "=", code)], limit=1)
        if not container:
            raise UserError(self.env._("No container has the code %s.", code))
        return container

    def _check_usable(self):
        """Refuse a container whose usable day has passed, or whose lot is not available. No usable day is not expiry."""
        today = self._today()
        for container in self:
            if container.usable_until and container.usable_until < today:
                raise UserError(self.env._("%s is past its usable date.", container.display_name))
            if not container.lot_id or container.lot_id.status != LOT_AVAILABLE:
                raise UserError(self.env._("The lot of %s is not available.", container.display_name))

    def _check_for_use(self, person):
        """The container is opened, still usable and in this person's store."""
        sealed = self.filtered(lambda container: container.status != CONTAINER_OPENED)
        if sealed:
            raise UserError(
                self.env._(
                    "Open %(containers)s before using them.",
                    containers=format_list(self.env, sealed.mapped("display_name")),
                )
            )
        self._check_usable()
        self._check_in_store(person)

    def _check_in_store(self, person, stores=None):
        stores = stores or person._store()
        outside = self.filtered(lambda container: not container._is_in(stores))
        if outside:
            raise UserError(
                self.env._(
                    "%(containers)s are not in a store of %(person)s.",
                    containers=format_list(self.env, outside.mapped("display_name")),
                    person=person.display_name,
                )
            )

    def _is_in(self, stores):
        self.ensure_one()
        location = self.sudo().location_id
        return bool(location) and location._holding_store() in stores

    def _settle(self, wasted):
        """A source container with nothing left is depleted, or disposed when the move wasted it."""
        empty = self.filtered(
            lambda container: (
                container.status in IN_STOCK_STATUSES
                and (not container.item_id or container.item_id.uom_id.is_zero(container.quantity))
            )
        )
        if empty:
            empty.sudo().write({"status": CONTAINER_DISPOSED if wasted else CONTAINER_DEPLETED})

    @api.model
    def _next_container_codes(self, lot_name, count):
        """The next count codes of containers of a lot, such as Lot123-01, numbered on from the codes already used."""
        prefix = f"{lot_name}-"
        used = self.sudo().search_fetch(Domain("name", "=like", f"{escape_like_value(prefix)}%"), ["name"])
        pattern = re.compile(rf"{re.escape(prefix)}(\d+)")
        numbers = [int(match.group(1)) for match in map(pattern.fullmatch, used.mapped("name")) if match]
        start = max(numbers, default=0) + 1
        return [f"{prefix}{number:02d}" for number in range(start, start + count)]
