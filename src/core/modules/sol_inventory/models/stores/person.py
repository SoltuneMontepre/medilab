from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOCATION
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON


# Nhân Sự
class Person(models.Model):
    _inherit = MODEL_PERSON

    @api.model
    def _for_user(self, user=None):
        """The person who signs in as this user. Read with full rights: the store rule is about who they are."""
        user = user or self.env.user
        person = self.sudo().search([("user_id", "=", user.id)], limit=1)
        if not person:
            raise UserError(self.env._("%s has no person record, so they have no store.", user.display_name))
        return person

    def _store(self):
        """The stores this person takes stock from: the stores their team holds, or, when they have no team or their
        team holds none, the stores their department holds."""
        self.ensure_one()
        stores = self.env[MODEL_STOCK_LOCATION]
        if self.team_id:
            stores = self._stores_of(self.team_id)
        if not stores and self.department_id:
            stores = self._stores_of(self.department_id)
        if not stores:
            raise UserError(
                self.env._(
                    "%s has no store. Their team and department hold none.",
                    self.display_name,
                )
            )
        return stores

    def _stores_of(self, holder):
        # Full rights: a tester may not be allowed to open the Stores screen, and the rule still names their store.
        return self.env[MODEL_STOCK_LOCATION].sudo().search([("is_store", "=", True), ("holder_id", "=", holder.id)])
