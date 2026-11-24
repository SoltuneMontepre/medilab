from typing import TYPE_CHECKING

from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE, STATE_REQUESTED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_MACHINE_BOOKING,
    MODEL_TASK,
    MODEL_TEST_RESULT,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskApprovalsBase
else:
    TaskApprovalsBase = object


# Nhiệm Vụ: the dashboard also lists what waits for the current person's approval or signature.
class TaskApprovals(models.Model, TaskApprovalsBase):
    _inherit = MODEL_TASK

    @api.model
    def get_dashboard_data(self):
        data = super().get_dashboard_data()
        data["to_approve"] = self._dashboard_approvals()
        return data

    @api.model
    def _dashboard_approvals(self):
        """The ids of the results, file versions and bookings the current person may approve or sign now."""
        results = self._readable_search(MODEL_TEST_RESULT, Domain("status", "=", STATE_REQUESTED))
        # ponytail: signing rights are checked per record; index the candidates if their number grows into thousands.
        versions = self._readable_search(
            MODEL_LABORATORY_FILE_VERSION, Domain("approval_state", "in", (STATE_NONE, STATE_REQUESTED))
        )
        bookings = self.env[MODEL_MACHINE_BOOKING]
        proposed = (
            Domain("status", "=", "proposed")
            & Domain("starts_at", "!=", False)
            & Domain("person_id", "!=", False)
            & bookings._permission_domain("edit")
        )
        return {
            "results": results.filtered("approval_can_sign").ids,
            "versions": versions.filtered("approval_can_sign").ids,
            "bookings": self._readable_search(MODEL_MACHINE_BOOKING, proposed).ids,
        }

    @api.model
    def _readable_search(self, model, domain):
        # Someone who cannot read the model has nothing of it to approve, and the dashboard still opens for them.
        records = self.env[model]
        return records.search(domain) if records.has_access("read") else records
