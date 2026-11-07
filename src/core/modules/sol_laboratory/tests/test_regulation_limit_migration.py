from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_REGULATION, MODEL_REGULATION_LIMIT, MODEL_SAMPLE_TYPE

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.26.0" / "pre-migrate.py"


@tagged("post_install", "-at_install")
class TestRegulationLimitMigration(MasterDataCase):
    """Before the upgrade, a regulation on food and water with one lead limit, and one naming no sample type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.food, cls.water = cls.env[MODEL_SAMPLE_TYPE].create([{"name": "Food"}, {"name": "Water"}])
        cls.cabbage = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "parent_id": cls.food.id})
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {"code": "QCVN 8-2:2011/BYT", "name": "Heavy metals in food", "sample_type_ids": (cls.food | cls.water).ids}
        )
        cls.limit = cls.env[MODEL_REGULATION_LIMIT].create(
            {
                "regulation_id": cls.regulation.id,
                "parameter_id": cls.parameter.id,
                "sample_type_id": cls.food.id,
                "unit_id": cls.unit.id,
                "max_set": True,
                "max_value": 0.3,
                "decimals": 1,
            }
        )
        cls.unscoped = cls.env[MODEL_REGULATION].create({"code": "QCVN 01:2009/BYT", "name": "Drinking water"})

    def old_limits(self):
        """The limits table before the upgrade, for this test's transaction only."""
        cr = self.env.cr
        cr.execute("ALTER TABLE medilab_regulation_limit DROP COLUMN sample_type_id")
        cr.execute(
            """
            INSERT INTO medilab_regulation_limit (regulation_id, parameter_id, limit_text, min_set, max_set)
            VALUES (%s, %s, '{"en_US": "Not detected"}', FALSE, FALSE)
            """,
            [self.unscoped.id, self.parameter.id],
        )
        self.env.invalidate_all()

    def test_upgrade_copies_each_limit_to_the_named_types_only_and_removes_unscoped_ones(self):
        self.old_limits()

        with self.assertLogs(level="WARNING") as logged:
            load_script(str(PRE_MIGRATE), "pre_migrate").migrate(self.env.cr, "20.0.1.25.0")
        self.env.invalidate_all()

        limits = self.regulation.limit_ids
        self.assertEqual(limits.sample_type_id, self.food | self.water)
        self.assertIn(self.limit, limits)
        for limit in limits:
            self.assertEqual((limit.max_value, limit.unit_id, limit.decimals), (0.3, self.unit, 1))
        self.assertFalse(self.unscoped.limit_ids)
        self.assertIn("QCVN 01:2009/BYT", " ".join(logged.output))
