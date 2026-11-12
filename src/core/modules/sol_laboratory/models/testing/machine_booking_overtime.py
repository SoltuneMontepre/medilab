from typing import TYPE_CHECKING

from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_OVERTIME

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingOverTimeBase
else:
    MachineBookingOverTimeBase = object


# Lịch Đặt Máy: a tester's planned OverTime adds to their working time.
class MachineBookingOverTime(models.Model, MachineBookingOverTimeBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.model
    def _working_time(self, person, start, end):
        """The person's working intervals plus their OverTime between start and end, merged where they meet. Machines
        and locations keep their own availability."""
        working = super()._working_time(person, start, end)
        if not person:
            return working
        overtimes = (
            self.env[MODEL_OVERTIME]
            .sudo()
            .search_fetch(
                Domain("person_id", "=", person.id) & Domain("starts_at", "<", end) & Domain("ends_at", ">", start),
                ["starts_at", "ends_at"],
            )
        )
        intervals = list(working)
        for overtime in overtimes:
            # Both are required; the check narrows their type.
            begin, finish = overtime.starts_at, overtime.ends_at
            if begin and finish:
                intervals.append((max(begin, start), min(finish, end)))
        merged = []
        for begin, finish in sorted(intervals):
            if merged and begin <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], finish))
            else:
                merged.append((begin, finish))
        return merged
