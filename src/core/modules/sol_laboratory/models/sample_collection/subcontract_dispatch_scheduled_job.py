from typing import TYPE_CHECKING

from odoo import models
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.jobs import DISPATCH_ACCREDITATION_LAPSED_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB, MODEL_SUBCONTRACT_DISPATCH
from odoo.addons.sol_laboratory.constants.notifications import EVENT_DISPATCH_ACCREDITATION_LAPSED

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_subcontract_dispatches_accreditation_lapsed(self):
        dispatches = (
            self.env[MODEL_SUBCONTRACT_DISPATCH]
            .sudo()
            .search([("status", "=", "draft"), ("subcontractor_id.accreditation_expired", "=", True)])
        )
        # One item for each expiry date, so a dispatch is told again after a renewal lapses in turn.
        for dispatch in dispatches:
            expiry = dispatch.subcontractor_id.accreditation_expiry
            self.queue(DISPATCH_ACCREDITATION_LAPSED_JOB, f"subcontract_dispatch:{dispatch.id}:{expiry}", dispatch)

    def _handle_subcontract_dispatches_accreditation_lapsed(self, item):
        dispatch = item._document()
        if not dispatch or not dispatch.exists() or dispatch.status != "draft":
            return
        subcontractor = dispatch.subcontractor_id
        if not subcontractor.accreditation_expired:
            return
        dispatch._notify_heads(
            EVENT_DISPATCH_ACCREDITATION_LAPSED,
            f"accreditation_lapsed:{subcontractor.accreditation_expiry}",
            self.env._(
                "The accreditation of %(subcontractor)s expired on %(date)s, so %(dispatch)s cannot be sent. Wait for "
                "the renewal, or cancel the dispatch and move its sample tests to another subcontractor with the same "
                "method.",
                subcontractor=subcontractor.name,
                date=format_date(self.env, subcontractor.accreditation_expiry),
                dispatch=dispatch.code,
            ),
        )
