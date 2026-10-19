from odoo import api, models

from odoo.addons.sol_commerce.constants.models import MODEL_NOTIFICATION_CONTACT
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE


# Thông Báo
class MailMessage(models.Model):
    _inherit = MODEL_MAIL_MESSAGE

    @api.model
    def _event_partners(self, event, partners):
        """Send a customer's event to the contact its business chose, when it chose one.

        A mandatory event still reaches the contact the document names."""
        collected = super()._event_partners(event, partners)
        routes = (
            self.env[MODEL_NOTIFICATION_CONTACT]
            .sudo()
            .search([("event_id", "=", event.id), ("partner_id", "in", collected.commercial_partner_id.ids)])
        )
        for route in routes.filtered(lambda route: route.contact_id.active and route.contact_id.email):
            replaced = collected.filtered(
                lambda partner, route=route: partner.commercial_partner_id == route.partner_id
            )
            collected = (collected if event.mandatory else collected - replaced) | route.contact_id
        return collected
