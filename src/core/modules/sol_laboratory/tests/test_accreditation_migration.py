from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_SAMPLE_TYPE,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.26.0" / "post-migrate.py"
# load_script names the module, and so the script's logger, after its second argument.
MIGRATION_LOGGER = "post_migrate"


@tagged("post_install", "-at_install")
class TestAccreditationMigration(MasterDataCase):
    """A certificate that listed two methods before scope lines, one of them already in a complete line."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sample_type = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled drinking water"})
        cls.applicability = cls.offer(cls.parameter, cls.sample_type)
        cls.other = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "MIG-OTHER", "name": "Other", "field_id": cls.testing_field.id}
        )
        cls.certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE].create({"code": "VILAS-MIG"})
        cls.complete = cls.env[MODEL_ACCREDITATION_SCOPE_LINE].create(
            {
                "certificate_id": cls.certificate.id,
                "method_id": cls.other.id,
                "parameter_ids": [persisted_id(cls.parameter)],
                "sample_type_ids": [persisted_id(cls.sample_type)],
            }
        )
        cls.env.cr.execute(
            """
            CREATE TABLE IF NOT EXISTS medilab_accreditation_certificate_method_rel
                   (certificate_id INTEGER NOT NULL, method_id INTEGER NOT NULL)
            """
        )
        cls.env.cr.execute(
            "INSERT INTO medilab_accreditation_certificate_method_rel VALUES (%s, %s), (%s, %s)",
            [cls.certificate.id, cls.method.id, cls.certificate.id, cls.other.id],
        )

    def migrate(self):
        with mute_logger(MIGRATION_LOGGER):
            load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.25.0")
        self.env.invalidate_all()

    def test_each_method_becomes_a_line_to_confirm_that_accredits_nothing(self):
        self.migrate()
        added = self.certificate.scope_line_ids - self.complete
        self.assertEqual(added.method_id, self.method)
        self.assertTrue(added.to_confirm)
        self.assertFalse(added.parameter_ids)
        self.assertFalse(added.sample_type_ids)
        self.env[MODEL_ACCREDITATION_CERTIFICATE]._recompute_accreditation(self.method)
        self.assertFalse(self.applicability.is_accredited)

    def test_a_method_already_in_a_line_is_not_added_again(self):
        self.migrate()
        self.assertEqual(len(self.certificate.scope_line_ids.filtered(lambda line: line.method_id == self.other)), 1)

    def test_running_twice_adds_nothing(self):
        self.migrate()
        lines = self.certificate.scope_line_ids
        self.migrate()
        self.assertEqual(self.certificate.scope_line_ids, lines)

    def test_lines_to_confirm_are_listed(self):
        with self.assertLogs(MIGRATION_LOGGER, "WARNING") as logs:
            load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.25.0")
        self.assertIn(f"VILAS-MIG – {self.method.code}", logs.output[0])

    def test_lines_to_confirm_are_found_by_the_certificate_filter(self):
        self.migrate()
        found = self.env[MODEL_ACCREDITATION_CERTIFICATE].search([("scope_line_ids.to_confirm", "=", True)])
        self.assertIn(self.certificate, found)
