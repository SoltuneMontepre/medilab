"""Uninstalling the other modules leaves the Laboratory data intact (SH-01).

Module operations cannot run inside a test case, so this is a standalone function that
``python3 -m odoo.tests.test_module_operations -d <database> standalone medilab_uninstall`` runs: ``task test:uninstall``.
"""

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tests.common import standalone

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_DEPARTMENT,
    MODEL_PERMISSION,
    MODEL_PERSON,
)
from odoo.addons.sol_laboratory.constants.xml_ids import MODULE
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model
from odoo.addons.sol_laboratory.services.record_id import persisted_id
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

PREFIX = "medilab."
OTHER_MODULES = ("sol_commerce", "sol_inventory")
# The audit trail records the records an uninstall deletes, so it only grows.
TRAIL = (MODEL_AUDIT_ENTRY, MODEL_AUDIT_CHANGE)


def _owned_ids(env, module):
    """Records of Laboratory models that belong to another module and leave with it."""
    data = env["ir.model.data"].search([("module", "=", module), ("model", "=like", f"{PREFIX}%")])
    owned = {}
    for row in data:
        owned.setdefault(row.model, []).append(row.res_id)
    return owned


def _laboratory_counts(env, owned=None):
    owned = owned or {}
    counts = {}
    for name, model in env.registry.items():
        if not name.startswith(PREFIX) or model._original_module != MODULE or model._abstract or model._transient:
            continue
        if name in TRAIL:
            continue
        domain = [("id", "not in", owned.get(name, []))] if owned.get(name) else []
        counts[name] = env[name].with_context(active_test=False).search_count(domain)
    return counts


def _permission_codes(env, module):
    data = env["ir.model.data"].search([("module", "=", module), ("model", "=", MODEL_PERMISSION)])
    return env[MODEL_PERMISSION].browse(data.mapped("res_id")).exists().mapped("code")


@standalone("medilab_uninstall")
def test_uninstalling_other_modules_keeps_laboratory_data(env):
    department = env[MODEL_DEPARTMENT].create({"name": "Chemistry"})
    person = env[MODEL_PERSON].create({"name": "Nguyen Van An", "department_id": department.id, "login": "an.nguyen"})
    env.cr.commit()
    for name in OTHER_MODULES:
        module = env["ir.module.module"].search([("name", "=", name)])
        if module.state != "installed":
            continue
        before = _laboratory_counts(env, _owned_ids(env, name))
        trail = {model: env[model].search_count([]) for model in TRAIL}
        codes = _permission_codes(env, name)
        module.button_immediate_uninstall()
        env = api.Environment(env.cr, SUPERUSER_ID, {})
        assert env["ir.module.module"].browse(persisted_id(module)).state == "uninstalled", f"{name} is still installed"
        for model, count in trail.items():
            assert dynamic_model(env, model).search_count([]) >= count, (
                f"uninstalling {name} removed records of {model}"
            )
        after = _laboratory_counts(env)
        changed = {
            key: (before.get(key), after.get(key))
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        assert after == before, f"uninstalling {name} changed the Laboratory data: {changed}"
        assert env[MODEL_DEPARTMENT].browse(department.id).exists(), "the department is gone"
        assert env[MODEL_PERSON].browse(person.id).user_id.exists(), "the person or their user is gone"
        assert not env["ir.model.data"].search([("module", "=", name)]), f"{name} left external ids behind"
        group_names = [f"Permission: {code}" for code in codes]
        assert not env["res.groups"].search([("name", "in", group_names)]), f"{name} left permission groups behind"
        generated = [
            f"{kind}_permission_{assert_instance(code, str).replace('.', '_')}"
            for code in codes
            for kind in ("group", "access")
        ]
        assert not env["ir.model.data"].search([("module", "=", MODULE), ("name", "in", generated)]), (
            f"{name} left generated external ids behind"
        )
