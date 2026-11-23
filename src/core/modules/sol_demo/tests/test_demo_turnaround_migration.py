from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.46.0" / "post-migrate.py"
TURNAROUNDS = {
    "lead_aas": 5,
    "lead_icpms": 5,
    "lead_subcontracted": 6,
    "coliforms_mpn": 5,
    "coliforms_colony": 4,
    "e_coli_membrane": 4,
    "e_coli_colony": 4,
    "ph_water": 2,
    "ph_soil": 3,
    "chlorpyrifos_quechers": 7,
    "chlorpyrifos_ug": 9,
    "chromium_vi_colorimetry": 3,
    "cadmium_icpms": 5,
    "arsenic_icpms": 5,
}


@tagged("post_install", "-at_install")
class TestDemoTurnaroundMigration(TransactionCase):
    def test_upgrade_restores_only_blank_turnarounds_from_the_xml_seed(self):
        ways = self.env[MODEL_PARAMETER_METHOD]
        methods = {name: reference_as(ways, f"sol_demo.demo_parameter_method_{name}") for name in TURNAROUNDS}
        for way in methods.values():
            way.turnaround_days = 0
        customized = methods["lead_aas"]
        non_seeded = customized.copy({"active": False, "turnaround_days": 0})

        self.assertTrue(POST_MIGRATE.is_file(), "The demo turnaround upgrade migration must exist.")
        migration = load_script(str(POST_MIGRATE), "demo_turnaround_post")
        migration.migrate(self.env.cr, "20.0.1.45.0")
        self.env.invalidate_all()

        self.assertEqual({name: way.turnaround_days for name, way in methods.items()}, TURNAROUNDS)

        customized.turnaround_days = 13
        migration.migrate(self.env.cr, "20.0.1.45.0")
        self.env.invalidate_all()

        self.assertEqual(
            {name: way.turnaround_days for name, way in methods.items()},
            TURNAROUNDS | {"lead_aas": 13},
        )
        self.assertFalse(non_seeded.turnaround_days)
