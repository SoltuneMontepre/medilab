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

    def _quality_registration_window(self):
        """Today in the laboratory and the last day whose dossiers are warned."""
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("quality_registration_warning_days")
        return today, today + timedelta(days=days)

    def _queue_quality_registration_expiry(self):
        today, horizon = self._quality_registration_window()
        registrations = (
            self.env[MODEL_QUALITY_REGISTRATION]
            .sudo()
            .search([("valid_until", ">=", today), ("valid_until", "<=", horizon)])
        )
        # One item for the warning before and one for the warning on each last valid day, so a renewed dossier is
        # warned again however often the job runs.
        for registration in registrations:
            kind = "today" if registration.valid_until == today else "soon"
            item_key = f"quality_registration:{registration.id}:{registration.valid_until}:{kind}"
            self.queue(QUALITY_REGISTRATION_EXPIRY_JOB, item_key, registration)

    def _handle_quality_registration_expiry(self, item):
        registration = item._document()
        if not registration or not registration.exists() or not registration.active or not registration.valid_until:
            return
        today, horizon = self._quality_registration_window()
        if not today <= registration.valid_until <= horizon:
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
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_QUALITY_REGISTRATION_EXPIRY,
            registration,
            f"quality_registration:{registration.id}:{registration.valid_until}:{kind}",
            body,
        )
