from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_PERMISSION


def migrate(cr, _version):
    # Ways of testing are archived, never deleted. Their delete permissions go with their groups and accesses; the
    # ways of testing stay. The external ids go first, as a permission that comes with a module cannot be deleted.
    env = api.Environment(cr, SUPERUSER_ID, {})
    permissions = env[MODEL_PERMISSION].search(
        [("document_model", "=", MODEL_PARAMETER_METHOD), ("action", "=", "delete")]
    )
    env["ir.model.data"].search([("model", "=", MODEL_PERMISSION), ("res_id", "in", permissions.ids)]).unlink()
    permissions.unlink()
