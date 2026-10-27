from datetime import timedelta

from odoo import models
from odoo.tools import format_date

from odoo.addons.sol_laboratory.constants.jobs import QUALITY_REGISTRATION_EXPIRY_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_MAIL_MESSAGE,
    MODEL_QUALITY_REGISTRATION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_QUALITY_REGISTRATION_EXPIRY


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_quality_registration_expiry(self):
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("quality_registration_warning_days")
        registrations = (
            self.env[MODEL_QUALITY_REGISTRATION]
            .sudo()
            .search([("valid_until", ">=", today), ("valid_until", "<=", today + timedelta(days=days))])
        )
        # The item key holds the day and the last valid day, so a dossier is queued once a day however often the job
        # runs, and again when it is renewed.
        for registration in registrations:
            item_key = f"quality_registration:{registration.id}:{registration.valid_until}:{today}"
            self.queue(QUALITY_REGISTRATION_EXPIRY_JOB, item_key, registration)

    def _handle_quality_registration_expiry(self, item):
        registration = item._document()
        if not registration or not registration.exists() or not registration.active or not registration.valid_until:
            return
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("quality_registration_warning_days")
        if not today <= registration.valid_until <= today + timedelta(days=days):
            return
        date = format_date(self.env, registration.valid_until)
        if registration.valid_until == today:
            kind = "today"
            body = self.env._(
                "The quality registration %(name)s expires today, %(date)s. From tomorrow its mark is no longer "
                "printed on reports.",
                name=registration.display_name,
                date=date,
            )
        else:
            kind = "soon"
            body = self.env._(
                "The quality registration %(name)s expires on %(date)s. Renew it before then, or its mark is no "
                "longer printed on reports.",
                name=registration.display_name,
                date=date,
            )
        # One warning before and one on the day for each last valid day, so a renewed dossier is warned again.
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_QUALITY_REGISTRATION_EXPIRY,
            registration,
            f"quality_registration:{registration.id}:{registration.valid_until}:{kind}",
            body,
        )
