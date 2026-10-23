from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SECTOR
from odoo.addons.sol_onboarding.constants.onboarding import SECTOR_CODES


@tagged("post_install", "-at_install")
class TestSectors(TransactionCase):
    def test_the_four_sectors_are_shipped(self):
        sectors = self.env[MODEL_ONBOARDING_SECTOR].search([])
        self.assertEqual(set(sectors.mapped("code")), set(SECTOR_CODES))

    def test_a_sector_code_is_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env[MODEL_ONBOARDING_SECTOR].create({"code": "food", "name": "Food again"})
