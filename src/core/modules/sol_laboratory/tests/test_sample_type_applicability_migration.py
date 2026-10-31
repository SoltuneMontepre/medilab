from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools.sql import column_exists

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SAMPLE_TYPE, MODEL_TESTING_METHOD

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.24.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestSampleTypeApplicabilityMigration(MasterDataCase):
    def test_upgrade_gives_only_the_default_way_the_sample_types_its_parameter_listed(self):
        cr = self.env.cr
        cabbage, water = self.env[MODEL_SAMPLE_TYPE].create([{"name": "Cabbage"}, {"name": "Bottled water"}])
        icp_ms = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.env[MODEL_TESTING_METHOD]
                .create({"code": "ISO 17294-2:2016", "name": "ICP-MS", "field_id": self.testing_field.id})
                .id,
                "department_id": self.department.id,
            }
        )
        # The columns and sample types of a way of testing before the upgrade, for this test's transaction only.
        cr.execute(
            """
            ALTER TABLE medilab_parameter_method
                ADD COLUMN unit_id integer,
                ADD COLUMN lod numeric,
                ADD COLUMN loq numeric,
                ADD COLUMN result_decimals integer,
                ADD COLUMN is_default boolean
            """
        )
        cr.execute(
            "UPDATE medilab_parameter_method SET unit_id = %s, lod = 0, loq = 0.03, result_decimals = 3, is_default = %s"
            " WHERE id = %s",
            [self.unit.id, True, self.pair.id],
        )
        cr.execute(
            "UPDATE medilab_parameter_method SET unit_id = %s, lod = 0.1, is_default = %s WHERE id = %s",
            [self.unit.id, False, icp_ms.id],
        )
        cr.execute(
            "INSERT INTO medilab_test_parameter_sample_type_rel (parameter_id, sample_type_id) VALUES (%s, %s), (%s, %s)",
            [self.parameter.id, cabbage.id, self.parameter.id, water.id],
        )
        self.env.invalidate_all()

        with self.assertLogs(level="WARNING") as logged:
            load_script(str(POST_MIGRATE), "post_migrate").migrate(cr, "20.0.1.21.0")

        applicabilities = self.parameter.applicability_ids
        self.assertEqual(applicabilities.parameter_method_id, self.pair)
        self.assertEqual(applicabilities.sample_type_id, cabbage | water)
        for applicability in applicabilities:
            self.assertEqual(applicability.unit_id, self.unit)
            self.assertIs(applicability.lod, False)
            self.assertEqual(applicability.loq, 0.03)
            self.assertEqual(applicability.result_decimals, 3)
            self.assertTrue(applicability.is_default)
        self.assertEqual(self.parameter.sample_type_ids, cabbage | water)
        warned = " ".join(logged.output)
        self.assertIn(f"Way of testing {icp_ms.id} of parameter {self.parameter.id} applies to no sample type", warned)
        self.assertNotIn(f"Way of testing {self.pair.id} ", warned)
        self.assertFalse(column_exists(cr, "medilab_parameter_method", "is_default"))
