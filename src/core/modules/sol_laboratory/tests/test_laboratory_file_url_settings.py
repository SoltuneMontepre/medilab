from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_FILE_URL_MINUTES,
    LONGEST_LABORATORY_FILE_URL_MINUTES,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFileUrlSettings(TransactionCase):
    def test_a_file_address_lasts_15_minutes_by_default(self):
        minutes = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_file_url_minutes")

        self.assertEqual(minutes, DEFAULT_LABORATORY_FILE_URL_MINUTES)

    def test_a_file_address_lasts_from_a_minute_to_7_days(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        for minutes in (1, LONGEST_LABORATORY_FILE_URL_MINUTES):
            with self.subTest(minutes=minutes):
                settings.create({"laboratory_file_url_minutes": minutes})
        for minutes in (0, LONGEST_LABORATORY_FILE_URL_MINUTES + 1):
            with self.subTest(minutes=minutes), self.assertRaises(ValidationError):
                settings.create({"laboratory_file_url_minutes": minutes})
