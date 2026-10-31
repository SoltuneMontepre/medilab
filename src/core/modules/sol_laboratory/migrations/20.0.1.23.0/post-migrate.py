from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE


def migrate(cr, _version):
    # A level replaced or removed during signing keeps its position among archived levels, so only active levels are
    # unique by position now.
    cr.execute("ALTER TABLE medilab_approval_level DROP CONSTRAINT IF EXISTS medilab_approval_level_sequence_unique")
    # Documents already being signed keep the levels their chain has now, as if their signing started today.
    env = api.Environment(cr, SUPERUSER_ID, {})
    rows = env[MODEL_SIGNATURE].search([("withdrawn_at", "=", False)])
    for model, document_id in {(row.document_model, row.document_id) for row in rows}:
        if model in env:
            document = env[model].browse(document_id).exists()
            if document:
                document._approval_start()
