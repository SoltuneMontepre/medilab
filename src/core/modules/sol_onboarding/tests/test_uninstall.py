"""Uninstalling Onboarding leaves the master data it accepted in Laboratory (SH-01).

A standalone function, like ``sol_laboratory/tests/test_uninstall.py``, which ``task test:uninstall`` runs after it.
"""

from datetime import datetime

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tests.common import standalone

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_FIELD, MODEL_TESTING_METHOD
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues

CODE = "TCVN 9999:2026"
NAME = "Phương pháp thử gỡ cài đặt"


@standalone("medilab_uninstall")
def test_uninstalling_onboarding_keeps_accepted_master_data(env):
    field = env[MODEL_TESTING_FIELD].create({"code": "ZZUNINSTALL", "name": "Uninstall field"})
    source = env[MODEL_ONBOARDING_SOURCE].create(
        {"name": "Uninstall source", "adapter": "test", "host": "lab.example", "start_url": "https://lab.example/"}
    )
    run = env[MODEL_ONBOARDING_RUN].create({})
    fetched = Fetched("https://lab.example/scope", "html", b"<p>Scope</p>", datetime(2026, 10, 21, 8, 0, 0))
    snapshot = env[MODEL_ONBOARDING_SNAPSHOT]._keep(run, source, fetched)
    values = {"code": CODE, "name": NAME, "field_key": ""}
    staged = env[MODEL_ONBOARDING_STAGED_RECORD]._stage(
        snapshot, [StagedValues(KIND_TESTING_METHOD, CODE, values, "vi_VN")]
    )
    staged.field_id = field
    staged.action_accept()
    assert staged.state == "accepted", staged.error
    method_id = staged.record_id
    env.cr.commit()

    module = env["ir.module.module"].search([("name", "=", "sol_onboarding")])
    module.button_immediate_uninstall()
    env = api.Environment(env.cr, SUPERUSER_ID, {})

    assert env["ir.module.module"].browse(module.id).state == "uninstalled", "sol_onboarding is still installed"
    method = env[MODEL_TESTING_METHOD].browse(method_id).exists()
    assert method, "the accepted testing method is gone"
    assert (method.code, method.name) == (CODE, NAME), f"the accepted testing method changed: {method.code}"
