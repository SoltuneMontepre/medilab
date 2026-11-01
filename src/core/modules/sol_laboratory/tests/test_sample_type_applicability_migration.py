from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools.sql import column_exists

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SAMPLE_TYPE, MODEL_TESTING_METHOD

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.24.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestSampleTypeApplicabilityMigration(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cabbage, cls.water = cls.env[MODEL_SAMPLE_TYPE].create([{"name": "Cabbage"}, {"name": "Bottled water"}])
        cls.icp_ms = cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cls.parameter.id,
                "method_id": cls.env[MODEL_TESTING_METHOD]
                .create({"code": "ISO 17294-2:2016", "name": "ICP-MS", "field_id": cls.testing_field.id})
                .id,
                "department_id": cls.department.id,
            }
        )

    def old_ways(self, lod, loq):
        """The columns and sample types of the ways of testing before the upgrade, for this test's transaction only: the
        pair is the default with the limits given, ICP-MS another way with a LOD of 0.1."""
        cr = self.env.cr
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
            "UPDATE medilab_parameter_method SET unit_id = %s, lod = %s, loq = %s, result_decimals = 3, is_default = %s"
            " WHERE id = %s",
            [self.unit.id, lod, loq, True, self.pair.id],
        )
        cr.execute(
            "UPDATE medilab_parameter_method SET unit_id = %s, lod = 0.1, is_default = %s WHERE id = %s",
            [self.unit.id, False, self.icp_ms.id],
        )
        cr.execute(
            "INSERT INTO medilab_test_parameter_sample_type_rel (parameter_id, sample_type_id) VALUES (%s, %s), (%s, %s)",
            [self.parameter.id, self.cabbage.id, self.parameter.id, self.water.id],
        )
        self.env.invalidate_all()

    def upgrade(self):
        with self.assertLogs(level="WARNING") as logged:
            load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.21.0")
        return " ".join(logged.output)

    def test_upgrade_gives_only_the_default_way_the_sample_types_its_parameter_listed(self):
        self.old_ways(0, 0.03)

        warned = self.upgrade()

        applicabilities = self.parameter.applicability_ids
        self.assertEqual(applicabilities.parameter_method_id, self.pair)
        self.assertEqual(applicabilities.sample_type_id, self.cabbage | self.water)
        for applicability in applicabilities:
            self.assertEqual(applicability.unit_id, self.unit)
            self.assertIs(applicability.lod, False)
            self.assertEqual(applicability.loq, 0.03)
            self.assertEqual(applicability.result_decimals, 3)
            self.assertTrue(applicability.is_default)
        self.assertEqual(self.parameter.sample_type_ids, self.cabbage | self.water)
        self.assertIn(
            f"Way of testing {self.icp_ms.id} (ISO 17294-2:2016) of parameter {self.parameter.id} "
            f"({self.parameter.name}) applies to no sample type",
            warned,
        )
        self.assertIn(f"it had unit {self.unit.name}, LOD 0.1, LOQ None and None decimals", warned)
        self.assertNotIn(f"Way of testing {self.pair.id} ", warned)
        self.assertFalse(column_exists(self.env.cr, "medilab_parameter_method", "is_default"))

    def test_upgrade_leaves_limits_that_were_never_valid_empty_and_logs_them(self):
        self.old_ways(0.5, 0.03)

        warned = self.upgrade()

        for applicability in self.parameter.applicability_ids:
            self.assertIs(applicability.lod, False)
            self.assertIs(applicability.loq, False)
        self.assertIn(f"Way of testing {self.pair.id} had LOD 0.5 and LOQ 0.03, which are not valid limits", warned)
