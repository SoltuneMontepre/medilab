import logging
from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

_logger = logging.getLogger(__name__)


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _handle_demo_echo(self, item):
        # The demo job writes its message to the log, and fails when the item asks it to, to show a retry.
        payload = item.payload or {}
        if payload.get("fail"):
            raise ValueError(payload.get("message") or "The demo item asked to fail")
        _logger.info("demo.echo: %s", payload.get("message"))
