import logging
from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.customers import SIGNUP_CUSTOMER_KEY
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

if TYPE_CHECKING:
    from medilab_model_types import Model_res_users as ResUsersBase
else:
    ResUsersBase = object

_logger = logging.getLogger(__name__)


# Người Dùng: a self-registered user is a customer's person; a password reset does not reveal who has an account.
class ResUsers(models.Model, ResUsersBase):
    _inherit = "res.users"

    @api.model
    def _signup_create_user(self, values):
        details = values.pop(SIGNUP_CUSTOMER_KEY, None)
        if details is None:
            return super()._signup_create_user(values)
        customers = self.env[MODEL_CUSTOMER].sudo()
        customers._check_signup_details(details)
        # The user is not kept when the customer cannot be created, because the sign-up page commits what it caught.
        with self.env.cr.savepoint():
            user = super()._signup_create_user(values)
            customers._create_from_signup(user, details)
        return user

    def reset_password(self, login):
        # The reset page answers the same whether or not the login has an account.
        matches = self.search_count(self._get_login_domain(login)) or self.search_count(self._get_email_domain(login))
        if matches != 1:
            _logger.info("Password reset asked for <%s>, which matches %s accounts", login, matches)
            return False
        return super().reset_password(login)
