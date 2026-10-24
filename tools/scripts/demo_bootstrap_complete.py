"""Mark a seeded demo bootstrap complete after the normal application is healthy."""

import os
from datetime import UTC, datetime

from odoo.addons.sol_demo.bootstrap import (
    BOOTSTRAP_OWNER_VARIABLE,
    bootstrap_state,
    set_bootstrap_state,
)

owner = os.environ[BOOTSTRAP_OWNER_VARIABLE]
odoo_env = locals()["env"]
state = bootstrap_state(odoo_env)
if not state or state.get("owner") != owner:
    raise RuntimeError("Demo bootstrap ownership does not match this isolated attempt")
if state.get("status") == "completed":
    print("Demo bootstrap is already complete.")
elif state.get("status") == "seeded":
    set_bootstrap_state(
        odoo_env,
        {
            "completed_at": datetime.now(UTC).isoformat(),
            "owner": owner,
            "status": "completed",
        },
    )
    odoo_env.cr.commit()
else:
    raise RuntimeError(
        f"Demo bootstrap cannot complete from state {state.get('status')!r}"
    )
