from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_MACHINE_METHOD
from odoo.addons.sol_laboratory.models.testing.machine_booking import _rooms_end, _round_up, _slot_length

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingProposalBase
else:
    MachineBookingProposalBase = object


# Lịch Đặt Máy: the tester puts their proposed booking in a slot and on a machine of their choice for the head to approve.
class MachineBookingProposal(models.Model, MachineBookingProposalBase):
    _inherit = MODEL_MACHINE_BOOKING

    def _propose(self, start, machine):
        """Put the proposed booking at start on the machine, linked to its testing method, where its tester, the machine
        and its rooms are free around the other pinned proposals. The plan keeps it there, pinned, until it is approved
        or returned to the plan."""
        self.ensure_one()
        self._check_adjustable()
        if self.status != "proposed":
            raise UserError(self.env._("Only a proposed booking takes a slot of your choice."))
        if not start:
            raise UserError(self.env._("Choose when %s starts.", self.display_name))
        start = _round_up(start)
        links = self.env[MODEL_MACHINE_METHOD].sudo().search([("method_id", "=", self.method_id.id)])
        way = self._proposed_way()
        if machine:
            link = links.filtered(lambda link: link.machine_id == machine)[:1]
            if not link:
                raise UserError(
                    self.env._(
                        "%(machine)s is not linked to the testing method of %(booking)s.",
                        machine=machine.display_name,
                        booking=self.display_name,
                    )
                )
            minutes = link.duration_minutes
        elif links:
            raise UserError(self.env._("Choose a machine for %s.", self.display_name))
        else:
            minutes = way.duration_minutes
        length = _slot_length(minutes)
        rooms = self._room_steps(way)
        department = self.sudo().department_id
        pinned = self.sudo().search(
            [
                ("department_id", "=", department.id),
                ("status", "=", "proposed"),
                ("is_pinned", "=", True),
                ("id", "!=", self.id),
            ]
        )
        until = start + max(length, _rooms_end(rooms))
        sample = self.sudo().sample_test_id.sample_id
        self._check_free(
            start, self._slot_availability(start, length, until, rooms, way, sample, machine=machine, planned=pinned)
        )
        self._set({"machine_id": machine.id, "starts_at": start, "ends_at": start + length, "is_pinned": True})
        self._plan(department)

    def action_return_to_plan(self):
        """Unpin proposed bookings so that the plan places them again."""
        self._check_adjustable()
        if any(booking.status != "proposed" for booking in self):
            raise UserError(self.env._("Only a proposed booking returns to the plan."))
        self._set({"is_pinned": False})
        self._plan(self.sudo().department_id)
