from typing import TYPE_CHECKING

from odoo import api, models
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_MACHINE_BOOKING,
    MODEL_PERSON,
    MODEL_RESOURCE_CALENDAR_LEAVES,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_resource_calendar_leaves as ResourceCalendarLeavesBase
else:
    ResourceCalendarLeavesBase = object

# Fields that change whom a leave takes away, and when.
LEAVE_FIELDS = frozenset({"resource_id", "date_from", "date_to", "count_as"})


# Nghỉ Phép
class ResourceCalendarLeaves(models.Model, ResourceCalendarLeavesBase):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_RESOURCE_CALENDAR_LEAVES
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_RESOURCE_CALENDAR_LEAVES]

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves._return_bookings()
        return leaves

    def write(self, vals):
        result = super().write(vals)
        if LEAVE_FIELDS & set(vals):
            self._return_bookings()
        return result

    def _return_bookings(self):
        """Return the scheduled bookings of the person on leave that it overlaps to the plan; a measurement already
        started stays."""
        # ponytail: company-wide time off entered after bookings were placed on it leaves them; return them here too
        # if public holidays are entered late.
        zone = self.env.company.tz or "UTC"
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        for leave in self.sudo().filtered(lambda leave: bool(leave.resource_id) and leave.count_as == "absence"):
            people = self.env[MODEL_PERSON].sudo().search([("employee_id.resource_id", "=", leave.resource_id.id)])
            if not people:
                continue
            bookings.search(
                [
                    ("person_id", "in", people.ids),
                    ("status", "=", "scheduled"),
                    ("starts_at", "<", leave.date_to),
                    ("ends_at", ">", leave.date_from),
                ]
            )._return_to_plan(
                self.env._(
                    "%(person)s is on leave from %(start)s to %(end)s.",
                    person=people[:1].display_name,
                    start=format_datetime(self.env, leave.date_from, tz=zone),
                    end=format_datetime(self.env, leave.date_to, tz=zone),
                )
            )
