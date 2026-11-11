import json

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_CONFIG_PARAMETER

BOOTSTRAP_MODE_VARIABLE = "MEDILAB_DEMO_BOOTSTRAP"
BOOTSTRAP_OWNER_VARIABLE = "MEDILAB_DEMO_BOOTSTRAP_OWNER"
BOOTSTRAP_STATE_KEY = "medilab.demo.bootstrap.state"


def bootstrap_state(env):
    raw = env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str(BOOTSTRAP_STATE_KEY)
    return json.loads(raw) if raw else None


def set_bootstrap_state(env, state):
    env[MODEL_IR_CONFIG_PARAMETER].sudo().set_str(BOOTSTRAP_STATE_KEY, json.dumps(state, sort_keys=True))
