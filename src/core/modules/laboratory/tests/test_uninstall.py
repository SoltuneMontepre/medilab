"""Uninstalling the other modules leaves the Laboratory data intact (SH-01).

Module operations cannot run inside a test case, so this is a standalone function that
``python3 -m odoo.tests.test_module_operations -d <database> standalone medilab_uninstall`` runs: ``task test:uninstall``.
"""

from odoo import SUPERUSER_ID, api
from odoo.tests.common import standalone

from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERMISSION, MODEL_PERSON
from odoo.addons.laboratory.constants.xml_ids import MODULE

PREFIX = "medilab."
OTHER_MODULES = ("commerce", "inventory")


def _laboratory_counts(env):
    return {
        name: env[name].with_context(active_test=False).search_count([])
        for name, model in env.registry.items()
        if name.startswith(PREFIX) and model._original_module == MODULE and not model._abstract and not model._transient
    }


def _permission_codes(env, module):
    data = env["ir.model.data"].search([("module", "=", module), ("model", "=", MODEL_PERMISSION)])
    return env[MODEL_PERMISSION].browse(data.mapped("res_id")).mapped("code")


@standalone("medilab_uninstall")
def test_uninstalling_other_modules_keeps_laboratory_data(env):
    department = env[MODEL_DEPARTMENT].create({"name": "Chemistry"})
    person = env[MODEL_PERSON].create({"name": "Nguyen Van An", "department_id": department.id, "login": "an.nguyen"})
    env.cr.commit()
    before = _laboratory_counts(env)
    for name in OTHER_MODULES:
        module = env["ir.module.module"].search([("name", "=", name)])
        if module.state != "installed":
            continue
        codes = _permission_codes(env, name)
        module.button_immediate_uninstall()
        env = api.Environment(env.cr, SUPERUSER_ID, {})
        assert env["ir.module.module"].browse(module.id).state == "uninstalled", f"{name} is still installed"
        assert _laboratory_counts(env) == before, f"uninstalling {name} changed the Laboratory data"
        assert env[MODEL_DEPARTMENT].browse(department.id).exists(), "the department is gone"
        assert env[MODEL_PERSON].browse(person.id).user_id.exists(), "the person or their user is gone"
        assert not env["ir.model.data"].search([("module", "=", name)]), f"{name} left external ids behind"
        group_names = [f"Permission: {code}" for code in codes]
        assert not env["res.groups"].search([("name", "in", group_names)]), f"{name} left permission groups behind"
        generated = [f"{kind}_permission_{code.replace('.', '_')}" for code in codes for kind in ("group", "access")]
        assert not env["ir.model.data"].search([("module", "=", MODULE), ("name", "in", generated)]), (
            f"{name} left generated external ids behind"
        )
