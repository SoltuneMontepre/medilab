from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_MACHINE_BOOKING,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_PLAN_REVISION,
    MODEL_PLAN_REVISION_MOVE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_plan_revision as PlanRevisionBase
else:
    PlanRevisionBase = object


# Phương Án Xếp Lại Lịch
class PlanRevision(models.Model, PlanRevisionBase):
    _name = MODEL_PLAN_REVISION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _audit_children = ("move_ids",)
    _description = "Plan Revision"
    _order = "id desc"
    _rec_name = "department_id"
    # The scheduler proposes revisions; heads only approve or reject them.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The department whose plan was recalculated.
        department_id = fields.Many2one(MODEL_DEPARTMENT, required=True, ondelete="restrict", index=True, readonly=True)
        # Why the plan was recalculated: the urgent work it makes room for.
        reason = fields.Text(required=True, readonly=True)
        # Proposed until every move to approve is approved, which applies it; rejected by a head; cancelled by a newer
        # recalculation. A proposed revision also keeps the moves held back until Sales records a customer's agreement.
        status = fields.Selection(
            [("proposed", "Proposed"), ("applied", "Applied"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
            required=True,
            default="proposed",
            readonly=True,
            index=True,
        )
        # The bookings the revision moves, holds back or finds in conflict.
        move_ids = fields.One2many(MODEL_PLAN_REVISION_MOVE, "revision_id", string="Moves", readonly=True)
        # True when the current user heads a department the revision affects and it is still proposed, so the form shows
        # the reject button.
        can_decide = fields.Boolean(compute="_compute_can_decide")
        # True when, besides, a move of their department waits for their approval, so the form shows the approve button.
        can_approve = fields.Boolean(compute="_compute_can_decide")

    @api.depends_context("uid")
    @api.depends("status", "move_ids.department_id", "move_ids.status")
    def _compute_can_decide(self):
        for revision in self:
            mine = (
                revision.move_ids._of_my_departments() if revision.status == "proposed" else revision.move_ids.browse()
            )
            revision.can_decide = bool(mine)
            revision.can_approve = any(move.status == "proposed" for move in mine)

    @api.model
    def _signature(self, moves):
        """What a set of moves proposes, to tell a recalculation that changes nothing from one that does: an approved
        move counts as the proposed move it was."""
        return {
            (
                move.booking_id.id,
                move.machine_id.id,
                move.starts_at,
                move.ends_at,
                move.status.replace("approved", "proposed"),
            )
            for move in moves
        }

    @api.model
    def _renew(self, department, rows, reason):
        """Make the department's open revision the one the recalculation gives: keep it when it proposes the same, cancel
        it and propose the new one otherwise, unless a head rejected that very revision. Each row is (booking, slot,
        status), a slot being (way, machine, start, length) as the scheduler finds it."""
        revisions = self.sudo()
        current = revisions.search([("department_id", "=", department.id), ("status", "=", "proposed")])
        values = [
            {
                "booking_id": booking.id,
                "department_id": department.id,
                "machine_id": machine.id,
                "previous_starts_at": booking.starts_at,
                "previous_ends_at": booking.ends_at,
                "starts_at": start,
                "ends_at": start + length,
                "status": status,
            }
            for booking, (_way, machine, start, length), status in rows
        ]
        wanted = {
            (vals["booking_id"], vals["machine_id"], vals["starts_at"], vals["ends_at"], vals["status"])
            for vals in values
        }
        if current and wanted == self._signature(current.move_ids):
            return
        current.status = "cancelled"
        if not wanted:
            return
        rejected = revisions.search(
            [("department_id", "=", department.id), ("status", "=", "rejected")], order="id desc", limit=1
        )
        if rejected and wanted == self._signature(rejected.move_ids):
            return
        revisions.create(
            {"department_id": department.id, "reason": reason, "move_ids": [(0, 0, vals) for vals in values]}
        )

    def action_approve(self):
        """The head of a department approves the moves of their department. The revision is applied once every move to
        approve is approved, by the head of each department."""
        person = self.env[MODEL_PERSON]._current()
        for revision in self:
            if revision.status != "proposed":
                raise UserError(self.env._("Only a proposed plan revision can be approved."))
            decidable = revision.move_ids._of_my_departments()
            if not decidable:
                raise AccessError(self.env._("Only the head of an affected department approves its moves."))
            mine = decidable.filtered(lambda move: move.status == "proposed")
            if not mine:
                raise UserError(self.env._("No move waits for your approval."))
            mine.sudo().write({"status": "approved", "approved_by_id": person.id})
            revision._apply_when_approved()

    def action_reject(self):
        """The head of an affected department rejects the revision: every booking keeps its slot, and the same
        recalculation is not proposed again."""
        for revision in self:
            if revision.status != "proposed":
                raise UserError(self.env._("Only a proposed plan revision can be rejected."))
            if not revision.move_ids._of_my_departments():
                raise AccessError(self.env._("Only the head of an affected department rejects its plan revision."))
            revision.sudo().status = "rejected"

    def _apply_when_approved(self):
        """Move the bookings when no move is left to approve; the moves held back or in conflict stay in the revision's
        record, and the plan is recalculated around the new slots."""
        self.ensure_one()
        revision = self.sudo()
        approved = revision.move_ids.filtered(lambda move: move.status == "approved")
        if not approved or revision.move_ids.filtered(lambda move: move.status == "proposed"):
            return
        approved._apply()
        revision.status = "applied"
        self.env[MODEL_MACHINE_BOOKING].sudo()._plan(revision.department_id)
        approved._notify_moved()
