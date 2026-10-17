from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_MOVE_LINE, MODEL_STOCK_PACKAGE
from odoo.addons.sol_inventory.constants.stock import DONE, RECEIPT_CODE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_ATTACHMENT

# What a done move moved; a mistake is corrected by another move.
DONE_LINE_FIELDS = frozenset(
    {
        "product_id",
        "quantity",
        "uom_id",
        "lot_id",
        "lot_name",
        "location_id",
        "location_dest_id",
        "package_id",
        "result_package_id",
    }
)


# Dòng Phiếu Nhập Kho: the part of a move from one lot and container, or into one.
class StockMoveLine(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_MOVE_LINE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_MOVE_LINE]

    # Number of bottles or vials the line receives of an item tracked by container; its quantity is split evenly
    # among them.
    container_count = fields.Integer(string="Bottles or Vials", required=True, default=1)
    # True when the line's item keeps each bottle or vial as a container of its own.
    track_containers = fields.Boolean(related="product_id.track_containers")
    # The manufacturer's certificate that came with the lot the line receives; it is attached to the lot.
    certificate_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="Manufacturer's Certificate", ondelete="set null")

    _container_count_positive = models.Constraint(
        "CHECK(container_count >= 1)", "A line receives at least one bottle or vial."
    )

    @api.constrains("location_dest_id")
    def _check_receipt_destination(self):
        # The receipt checks its own destination; only lines put elsewhere are checked again.
        self.filtered(
            lambda line: line.picking_code == RECEIPT_CODE and line.location_dest_id != line.picking_id.location_dest_id
        ).location_dest_id._check_in_central_store()

    def _compute_expiration_date(self):
        # The expiry of a lot received for a stock item is the date printed on its container, typed by the storekeeper;
        # Odoo's default of the receipt date plus the item's expiration time would invent one.
        typed = self.filtered(
            lambda line: (
                line.product_id.item_kind
                and line.picking_type_use_create_lots
                and not (line.quant_id.lot_id or line.lot_id)
            )
        )
        for line in typed:
            line.expiration_date = line.expiration_date or False
        return super(StockMoveLine, self - typed)._compute_expiration_date()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filtered("certificate_id")._hold_certificates()
        return lines

    def write(self, vals):
        if DONE_LINE_FIELDS & set(vals) and any(line.state == DONE for line in self):
            raise UserError(self.env._("Done moves are never changed; correct a mistake with another move."))
        result = super().write(vals)
        if vals.get("certificate_id"):
            self._hold_certificates()
        return result

    def _hold_certificates(self):
        """Keep an uploaded certificate on its line until the receipt attaches it to the lot, so whoever reads the
        receipt reads the certificate."""
        for line in self.filtered(lambda line: not line.certificate_id.res_id):
            line.certificate_id.sudo().write({"res_model": line._name, "res_id": line.id})

    def _check_expiry_typed(self):
        """Refuse receiving a lot of an item with an expiry date without the date printed on its container."""
        missing = self.filtered(
            lambda line: line.quantity and line.product_id.use_expiration_date and not line.expiration_date
        )
        if missing:
            raise UserError(
                self.env._(
                    "Type the expiry date printed on the container of: %s.",
                    format_list(self.env, missing.product_id.mapped("display_name")),
                )
            )

    def _put_in_containers(self):
        """Put each bottle or vial received of an item tracked by container in a sealed container of its own, coded
        after its lot, and split the line's quantity evenly among them."""
        packages = self.env[MODEL_STOCK_PACKAGE].sudo()
        for line in self.filtered(lambda line: line.product_id.track_containers and line.quantity > 0):
            lot_name = line.lot_id.name or line.lot_name
            if not lot_name or line.result_package_id:
                continue
            count = line.container_count
            share = line.uom_id.round(line.quantity / count)
            quantities = [share] * (count - 1) + [line.uom_id.round(line.quantity - share * (count - 1))]
            if line.uom_id.compare(min(quantities), 0) <= 0:
                raise UserError(
                    self.env._(
                        "%(quantity)s %(unit)s of %(item)s cannot be shared among %(count)s bottles or vials.",
                        quantity=line.quantity,
                        unit=line.uom_id.name,
                        item=line.product_id.display_name,
                        count=count,
                    )
                )
            containers = packages.create([{"name": code} for code in packages._next_container_codes(lot_name, count)])
            line.write({"quantity": quantities[0], "result_package_id": containers[0].id, "container_count": 1})
            copy = line.copy_data({"move_id": line.move_id.id, "expiration_date": line.expiration_date})[0]
            self.create(
                [
                    {**copy, "quantity": quantity, "result_package_id": container.id}
                    for quantity, container in zip(quantities[1:], containers[1:], strict=True)
                ]
            )

    def _attach_certificates(self):
        """Attach each received lot's manufacturer's certificate to the lot."""
        certificates = {line.lot_id: line.certificate_id for line in self.filtered("certificate_id") if line.lot_id}
        for lot, certificate in certificates.items():
            certificate.sudo().write({"res_model": lot._name, "res_id": lot.id})
            lot.sudo().certificate_id = certificate
