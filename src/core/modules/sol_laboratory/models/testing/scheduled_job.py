from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.jobs import AT_RISK_SUMMARY_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_MAIL_MESSAGE,
    MODEL_SAMPLE_TEST,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_SAMPLE_TEST_AT_RISK

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_sample_tests_at_risk_summary(self):
        # One summary a day for each tester and head of department with a sample test still at risk.
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        for partner in self.env[MODEL_SAMPLE_TEST].sudo().search([("at_risk", "=", True)])._risk_partners():
            self.queue(AT_RISK_SUMMARY_JOB, f"at_risk_summary:{partner.id}:{today}", partner)

    def _handle_sample_tests_at_risk_summary(self, item):
        partner = item._document()
        if not partner or not partner.exists():
            return
        tests = (
            self.env[MODEL_SAMPLE_TEST]
            .sudo()
            .search([("at_risk", "=", True)])
            .filtered(lambda test: partner in test._risk_partners())
        )
        if not tests:
            return
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_SAMPLE_TEST_AT_RISK,
            partner,
            item.item_key,
            self.env._(
                "Sample tests still at risk of missing their internal due date: %s",
                ", ".join(f"{test.sample_id.code}: {test.display_name}" for test in tests),
            ),
            partners=partner,
        )
