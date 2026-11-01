from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_MIXIN, MODEL_SIGNATURE
from odoo.addons.sol_laboratory.services.model_lookup import model_as


def migrate(cr, _version):
    # Documents already being signed keep the levels their chain has now, as if their signing started today. This runs
    # once every module is upgraded, so the document types other modules sign, such as purchase orders, have the
    # approval mixin.
    env = api.Environment(cr, SUPERUSER_ID, {})
    rows = env[MODEL_SIGNATURE].search([("withdrawn_at", "=", False)])
    for model, document_id in {(row.document_model, row.document_id) for row in rows}:
        if isinstance(model, str) and model in env:
            document = model_as(env, model, env[MODEL_APPROVAL_MIXIN]).browse(document_id).exists()
            if document:
                document._approval_start()
