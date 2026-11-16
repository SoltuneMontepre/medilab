from odoo import Command, api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_TEST_REPORT


def migrate(cr, _version):
    # Nobody edits a report: its edit permission goes, and the roles and people who held it deliver reports, and raise
    # change requests on issued ones, with the deliver permission. The external ids go first, as a permission that
    # comes with a module cannot be deleted.
    env = api.Environment(cr, SUPERUSER_ID, {})
    permissions = env[MODEL_PERMISSION]
    edit = permissions.search([("document_model", "=", MODEL_TEST_REPORT), ("action", "=", "edit")])
    deliver = permissions.search(
        [("document_model", "=", MODEL_TEST_REPORT), ("action", "=", "deliver"), ("scope", "=", "all")]
    )
    for holders in (edit.role_ids, edit.person_ids):
        holders.write({"permission_ids": [Command.link(deliver.id)]})
    env["ir.model.data"].search([("model", "=", MODEL_PERMISSION), ("res_id", "in", edit.ids)]).unlink()
    edit.unlink()
