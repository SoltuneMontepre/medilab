from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_OVERTIME,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_overtime as OverTimeBase
else:
    OverTimeBase = object


# Làm Thêm Giờ
class OverTime(models.Model, OverTimeBase):
    _name = MODEL_OVERTIME
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "OverTime"
    _order = "starts_at desc, id desc"
    _rec_name = "person_id"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The tester who works the OverTime.
        person_id = fields.Many2one(MODEL_PERSON, string="Tester", required=True, ondelete="restrict")
        # The tester's department, whose head records and changes the OverTime.
        department_id = fields.Many2one(related="person_id.department_id", store=True, index=True)
        # Start of the OverTime.
        starts_at = fields.Datetime(string="Start", required=True)
        # End of the OverTime.
        ends_at = fields.Datetime(string="End", required=True)
        # Why the OverTime is planned, such as urgent work that would otherwise miss its due date.
        reason = fields.Text(required=True)

    _person_start_idx = models.Index("(person_id, starts_at)")
    _period = models.Constraint("CHECK(ends_at > starts_at)", "OverTime ends after it starts.")
    _no_overlap = models.Constraint(
        "EXCLUDE USING gist (person_id WITH =, tsrange(starts_at, ends_at) WITH &&)",
        "The tester already has OverTime at that time.",
    )

    def _auto_init(self):
        # The overlap constraint compares people with a GiST index, which needs btree_gist.
        self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        return super()._auto_init()
