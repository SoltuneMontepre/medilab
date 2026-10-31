from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE


def migrate(cr, _version):
    # Documents already being signed keep the levels their chain has now, as if their signing started today. It runs
    # once every module is loaded, so documents of modules that depend on Laboratory, such as purchase orders, are
    # signed documents by then.
    env = api.Environment(cr, SUPERUSER_ID, {})
    rows = env[MODEL_SIGNATURE].search([("withdrawn_at", "=", False)])
    for model, document_id in {(row.document_model, row.document_id) for row in rows}:
        if model in env:
            document = env[model].browse(document_id).exists()
            if document:
                document._approval_start()
