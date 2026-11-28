from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PERSON,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES, _slot_length

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultMachineBase
else:
    TestResultMachineBase = object


# Kết Quả Thử Nghiệm: the machine the tester books for a draft result measured without one.
class TestResultMachine(models.Model, TestResultMachineBase):
    _inherit = MODEL_TEST_RESULT

    if not TYPE_CHECKING:
        # True when the current user entered the draft result, it has no machine, is measured in-house and its way's
        # testing method is linked to a machine.
        can_book_machine = fields.Boolean(compute="_compute_can_book_machine")
        # The machines linked to the way's testing method that are fit to use and have no other booking from the
        # result's start for the duration of the method on them; empty when no machine can be booked.
        available_machine_ids = fields.Many2many(
            MODEL_MACHINE, compute="_compute_available_machine_ids", string="Available Machines"
        )

    @api.depends_context("uid")
    @api.depends("status", "machine_id", "subcontractor_id", "entered_by_id", "parameter_method_id")
    def _compute_can_book_machine(self):
        for result in self:
            result.can_book_machine = bool(
                result.id
                and result.status == STATE_NONE
                and not result.machine_id
                and not result.subcontractor_id
                and result.entered_by_id == self.env.user
                and result._machine_links()
            )

    @api.depends_context("uid")
    @api.depends("can_book_machine", "started_at", "entered_at")
    def _compute_available_machine_ids(self):
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        for result in self:
            free = self.env[MODEL_MACHINE]
            for link in result._machine_links() if result.can_book_machine else []:
                start, end = result._measurement_interval(link)
                machine = link.machine_id
                busy = bookings.search_count(
                    [
                        ("machine_id", "=", machine.id),
                        ("status", "in", ACTIVE_STATUSES),
                        ("starts_at", "<", end),
                        ("ends_at", ">", start),
                    ],
                    limit=1,
                )
                if not busy and not bookings._machine_refusal(machine, start, end):
                    free |= machine
            result.available_machine_ids = free

    def _machine_links(self):
        """The links of the way's testing method to its machines."""
        self.ensure_one()
        method = self.sudo().parameter_method_id.method_id
        links = self.env[MODEL_MACHINE_METHOD].sudo()
        return links.search([("method_id", "=", method.id)]) if method else links

    def _measurement_interval(self, link):
        """From the result's start, or its entry when it has none, for the duration of the method on the machine."""
        self.ensure_one()
        start = self.started_at or self.entered_at
        return start, start + _slot_length(link.duration_minutes)

    def _book_machine(self, machine):
        """Book the machine for the measurement of the draft result, as a done booking of its tester, and take it as the
        result's booking and machine."""
        self.ensure_one()
        if not self.can_book_machine:
            raise UserError(
                self.env._("Only the tester who entered a draft result without a machine books a machine for it.")
            )
        # Two testers booking the same machine at once wait for each other, so the later one sees the earlier booking.
        self.env.cr.execute(
            SQL(
                "SELECT id FROM %s WHERE id = %s FOR UPDATE",
                SQL.identifier(self.env[MODEL_MACHINE]._table),
                machine.id,
            )
        )
        self.invalidate_recordset(["available_machine_ids"])
        if machine not in self.available_machine_ids:
            raise UserError(
                self.env._(
                    "%(machine)s is not free for the measurement of %(result)s.",
                    machine=machine.display_name,
                    result=self.display_name,
                )
            )
        link = self._machine_links().filtered(lambda link: link.machine_id == machine)[:1]
        start, end = self._measurement_interval(link)
        test = self.sudo().sample_test_id
        booking = (
            self.env[MODEL_MACHINE_BOOKING]
            .sudo()
            .create(
                {
                    "machine_id": machine.id,
                    "sample_test_id": test.id,
                    "task_id": test._latest_testing_task().id,
                    "person_id": self.env[MODEL_PERSON]._current().id,
                    "starts_at": start,
                    "ends_at": end,
                    "status": "done",
                }
            )
        )
        self.sudo().write({"booking_id": booking.id, "machine_id": machine.id})
