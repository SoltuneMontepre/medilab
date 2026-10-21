"""Route options that addons read and odoo.http does not declare, passed to http.route by unpacking."""

from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_KEY_SCOPE

# website=True makes a route a frontend page. The http_routing addon reads it, and odoo.http does not declare it among
# the route options, so pyright rejects it as a keyword.
FRONTEND_PAGE = {"website": True}
# The laboratory files API takes only the keys of signed-in computers. odoo.http reads bearer_scope for auth="bearer"
# and does not declare it among the route options.
DEVICE_KEY = {"bearer_scope": DEVICE_KEY_SCOPE}
