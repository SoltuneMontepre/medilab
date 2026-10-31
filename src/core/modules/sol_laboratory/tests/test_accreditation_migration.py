from pathlib import Path

from odoo.fields import Command
from odoo.modules.module import load_script
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_METHOD,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.7.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestAccreditationMigration(MasterDataCase):
    def test_upgrade_keeps_only_accreditation_a_certificate_supports(self):
        self.env[MODEL_ACCREDITATION_CERTIFICATE].create(
            {"code": "VILAS-MIG", "method_ids": [Command.set(persisted_ids(self.method))]}
        )
        uncertified_method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "MIG-NONE", "name": "Not on a certificate", "field_id": self.testing_field.id}
        )
        uncertified = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": uncertified_method.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
            }
        )
        subcontracted = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": self.env[MODEL_SUBCONTRACTOR].create({"name": "Migration Sub"}).id,
            }
        )
        pairs = self.pair | uncertified | subcontracted
        pairs.flush_recordset()
        # Values set by hand before the mark was worked out from certificates.
        self.env.cr.execute(
            "UPDATE medilab_parameter_method SET is_accredited = TRUE WHERE id IN %s", [tuple(pairs.ids)]
        )
        self.env.invalidate_all()

        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.6.0")

        self.env.invalidate_all()
        self.assertTrue(self.pair.is_accredited)
        self.assertFalse(uncertified.is_accredited)
        self.assertFalse(subcontracted.is_accredited)
