from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.sol_laboratory.constants.customers import SIGNUP_CUSTOMER_KEY
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS

CUSTOMER_FIELDS = ("customer_type", "company_name", "phone", "street", "city", "vat", "citizen_id")
# The sign-up page keeps these values when it shows an error, so the visitor does not type them again.
SIGN_UP_REQUEST_PARAMS.update(CUSTOMER_FIELDS)


class CustomerSignup(AuthSignupHome):
    def _prepare_signup_values(self, qcontext, *, validate_email=False):
        values = super()._prepare_signup_values(qcontext, validate_email=validate_email)
        # An invitation or a password reset carries a token; only a new sign-up registers a customer.
        if not qcontext.get("token"):
            values[SIGNUP_CUSTOMER_KEY] = {key: qcontext.get(key) for key in CUSTOMER_FIELDS}
        return values
