import logging

from odoo import models

from odoo.addons.laboratory.constants.models import MODEL_SCHEDULED_JOB

_logger = logging.getLogger(__name__)


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _handle_demo_echo(self, item):
        # The demo job writes its message to the log, and fails when the item asks it to, to show a retry.
        payload = item.payload or {}
        if payload.get("fail"):
            raise ValueError(payload.get("message") or "The demo item asked to fail")
        _logger.info("demo.echo: %s", payload.get("message"))
