from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_ACCREDITATION_CERTIFICATE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as


def migrate(cr, _version):
    # The Laboratory upgrade turned the methods of the demo certificates into lines to confirm; the demo data now states
    # their full scope, so those lines are left over.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in ("demo_accreditation_certificate_valid", "demo_accreditation_certificate_expired"):
        certificate = reference_as(env[MODEL_ACCREDITATION_CERTIFICATE], f"sol_demo.{name}", raise_if_not_found=False)
        if certificate:
            certificate.scope_line_ids.filtered("to_confirm").unlink()
