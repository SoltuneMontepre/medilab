from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_IR_ATTACHMENT,
    MODEL_LOCATION,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_location as LocationBase
else:
    LocationBase = object

IMAGE_MAX_SIZE = 4096


# Vị Trí
class Location(models.Model, LocationBase):
    _name = MODEL_LOCATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Location"
    _parent_store = True
    _order = "code"
    _rec_names_search = ("code", "name")
    _permission_actions = ("create", "edit", "archive", "delete")

    if not TYPE_CHECKING:
        # Unique code of the location, such as RO-01.
        code = fields.Char(required=True, copy=False, index="trigram")
        # Name of the location in each language.
        name = fields.Char(required=True, translate=True, index="trigram")
        # The broader location this one is in; empty for a top-level location.
        parent_id = fields.Many2one(MODEL_LOCATION, string="Inside", ondelete="restrict", index=True)
        # Ids of the location and all its ancestors, such as 1/4/9/, so finding the locations under one takes one query.
        parent_path = fields.Char(index=True)
        # Locations inside this one.
        child_ids = fields.One2many(MODEL_LOCATION, "parent_id", string="Locations Inside")
        # The department that uses the location.
        department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="set null", index=True, domain=DEPARTMENT_DOMAIN)
        # Attachment holding the picture of the location, such as a floor plan; the map the locations inside it are placed on.
        image_attachment_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="Image File", ondelete="set null", copy=False)
        # The picture itself, read from and saved to its attachment.
        image = fields.Image(
            compute="_compute_image", inverse="_inverse_image", max_width=IMAGE_MAX_SIZE, max_height=IMAGE_MAX_SIZE
        )
        # Horizontal position on the parent location's image, as a share of its width from 0 to 1; empty when not placed.
        map_x = fields.Float(string="Map X")
        # Vertical position on the parent location's image, as a share of its height from 0 to 1; empty when not placed.
        map_y = fields.Float(string="Map Y")
        # True when people can book the location on their calendar.
        is_bookable = fields.Boolean(string="Bookable")
        # False when the location is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a location must be unique.")
    _map_point_range = models.Constraint(
        "CHECK(map_x BETWEEN 0 AND 1 AND map_y BETWEEN 0 AND 1)",
        "A point on a map lies between 0 and 1 of the image's width and height.",
    )

    @api.depends("code", "name")
    def _compute_display_name(self):
        for location in self:
            location.display_name = f"{location.code or ''} {location.name or ''}".strip()

    @api.depends("image_attachment_id")
    def _compute_image(self):
        for location in self:
            location.image = location.image_attachment_id.raw or False

    def _inverse_image(self):
        for location in self:
            old = location.image_attachment_id
            location.image_attachment_id = (
                self.env[MODEL_IR_ATTACHMENT].create(
                    {"name": location.code, "raw": location.image, "res_model": self._name, "res_id": location.id}
                )
                if location.image
                else False
            )
            # The picture belongs only to the location.
            old.unlink()

    def get_map(self):
        """The location's picture and the locations inside it that are placed on it, for the map view.

        A child at the top left corner, 0 and 0, counts as not placed: Odoo reads an empty number as 0.
        """
        self.ensure_one()
        children = self.child_ids.filtered(lambda child: bool(child.map_x or child.map_y))
        return {
            "name": self.display_name,
            "image_id": self.image_attachment_id.id,
            "points": [
                {"id": child.id, "code": child.code, "name": child.display_name, "x": child.map_x, "y": child.map_y}
                for child in children
            ],
        }

    def action_open_bookings(self):
        """The bookings of the location and of the locations under it, such as the rooms of a floor."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sol_laboratory.action_medilab_location_booking")
        action["domain"] = [("location_id", "child_of", self.id)]
        action["context"] = {"default_location_id": self.id} if self.is_bookable else {}
        return action
