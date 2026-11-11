"""Route options that addons read and odoo.http does not declare, passed to http.route by unpacking."""

from typing import TypedDict

from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_KEY_SCOPE


class FrontendPageOptions(TypedDict):
    website: bool


class DeviceKeyOptions(TypedDict):
    bearer_scope: str


# http_routing reads website; the core route options do not declare it.
FRONTEND_PAGE: FrontendPageOptions = {"website": True}
# The laboratory files API takes only the keys of signed-in computers. odoo.http reads bearer_scope for auth="bearer"
# and does not declare it among the route options.
DEVICE_KEY: DeviceKeyOptions = {"bearer_scope": DEVICE_KEY_SCOPE}
