from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE


# Nguồn Tin Cậy
class OnboardingSource(models.Model):
    _name = MODEL_ONBOARDING_SOURCE
    _description = "Onboarding Source"
    _order = "id"

    _delay_seconds_not_negative = models.Constraint(
        "CHECK(delay_seconds >= 0)", "The delay between two requests cannot be negative."
    )
    _page_limit_positive = models.Constraint("CHECK(page_limit > 0)", "A run fetches at least one page.")

    # Source name in each language.
    name = fields.Char(string="Name", required=True, translate=True)
    # Key of the adapter that reads the source, such as boa.
    adapter = fields.Char(string="Adapter", required=True)
    # The only host runs of the source read from, such as www.boa.gov.vn.
    host = fields.Char(string="Host", required=True)
    # HTTPS address runs and organisation refreshes start from.
    start_url = fields.Char(string="Start Address", required=True)
    # Least seconds between two requests to the source.
    delay_seconds = fields.Integer(string="Delay (Seconds)", default=2)
    # Most pages one run fetches.
    page_limit = fields.Integer(string="Page Limit", default=500)
    # True when the developers turned the source on; runs read only turned-on sources.
    enabled = fields.Boolean(string="Enabled", default=False)
    # Time of the last request to the source, read and written under a row lock to keep the delay across workers.
    last_request_at = fields.Datetime(string="Last Request At")
    # Time the organisations of the source were last refreshed.
    organisations_refreshed_at = fields.Datetime(string="Organisations Refreshed At")
    # False when the developers retired the source; its snapshots and staged records keep it.
    active = fields.Boolean(string="Active", default=True)

    @api.constrains("host", "start_url")
    def _check_start_url(self):
        for source in self:
            try:
                address = urlsplit(source.start_url)
                valid = (
                    address.scheme == "https"
                    and address.hostname == source.host
                    and address.username is None
                    and address.port is None
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValidationError(
                    self.env._("The start address must be an HTTPS address on the host, without user or port.")
                )
