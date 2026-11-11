"""Print the bootstrap state from an Odoo shell cursor without changing it."""

import json

from odoo.addons.sol_demo.bootstrap import bootstrap_state

odoo_env = locals()["env"]
print(json.dumps(bootstrap_state(odoo_env) or {}))
