"""Route options that addons read and odoo.http does not declare, passed to http.route by unpacking."""

# website=True makes a route a frontend page. The http_routing addon reads it, and odoo.http does not declare it among
# the route options, so pyright rejects it as a keyword.
FRONTEND_PAGE = {"website": True}
