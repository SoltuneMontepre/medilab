from pathlib import Path

from freezegun import freeze_time

from odoo.modules.module import load_script
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY

PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.27.0" / "pre-migrate.py"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestResultSnapshotMigration(ResultCase):
    """A lead result and an arsenic result entered before the upgrade, whose way of testing on the sample's type
    detects 0.002 mg/g."""

    def test_upgrade_copies_the_way_sample_type_detection_limits_and_regulation_of_existing_results(self):
        self.applicability.lod = 0.002
        lead = self.enter()
        arsenic = self.enter(test=self.add_test())
        self.env.flush_all()
        cr = self.env.cr
        cr.execute(
            """
            ALTER TABLE medilab_test_result
                DROP COLUMN parameter_method_id,
                DROP COLUMN sample_type_id,
                DROP COLUMN lod,
                DROP COLUMN loq,
                DROP COLUMN regulation_id,
                DROP COLUMN comparison_requested
            """
        )
        self.env.invalidate_all()

        load_script(str(PRE_MIGRATE), "pre_migrate").migrate(cr, "20.0.1.26.0")
        self.env.invalidate_all()

        self.assertEqual((lead.parameter_method_id, lead.sample_type_id), (self.pair, self.sample_type))
        self.assertEqual((lead.lod, lead.loq), (0.002, False))
        self.assertEqual(lead.regulation_id, self.sample.regulation_id)
        self.assertTrue(lead.comparison_requested)
        self.assertFalse(arsenic.comparison_requested)
        self.assertEqual(lead.limit_max, 0.01, "The limit copied before the upgrade stays.")
