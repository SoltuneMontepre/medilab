from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.jobs import QUALITY_REGISTRATION_EXPIRY_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_QUALITY_REGISTRATION,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.settings import QUALITY_REGISTRATION_WARNING_PARAMETER
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_PERSON

EXPIRY_EVENT = "sol_laboratory.event_quality_registration_expiry"


@tagged("post_install", "-at_install")
class TestQualityRegistrationExpiry(TransactionCase):
    """Administrators are warned 7 days before a dossier's last valid day and on that day."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.env.ref(ADMINISTRATOR_PERSON).user_id
        cls.administrator.partner_id.email = "admin@anphu.example"
        cls.env[MODEL_RES_CONFIG_SETTINGS].create({"quality_registration_warning_days": 7}).execute()
        cls.today = cls.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        # Dossiers the database already holds, such as the demo data's, take no part in these warnings.
        cls.env[MODEL_QUALITY_REGISTRATION].search([]).active = False
        cls.registration = cls.env[MODEL_QUALITY_REGISTRATION].create(
            {"name": "Nuoc uong dong chai", "valid_until": cls.today + timedelta(days=3), "report_mark": "(*)"}
        )

    def run_job(self):
        self.env[MODEL_SCHEDULED_JOB]._run_key(QUALITY_REGISTRATION_EXPIRY_JOB)

    def warnings(self):
        return self.env["mail.message"].search(
            [
                ("model", "=", MODEL_QUALITY_REGISTRATION),
                ("res_id", "=", self.registration.id),
                ("subtype_id", "=", self.env.ref(EXPIRY_EVENT).id),
            ]
        )

    def test_the_warning_days_are_saved_from_the_settings_screen(self):
        self.assertEqual(self.env["ir.config_parameter"].get_int(QUALITY_REGISTRATION_WARNING_PARAMETER), 7)

    def test_a_negative_number_of_warning_days_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "cannot be negative"):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"quality_registration_warning_days": -1})

    def test_administrators_are_warned_once_before_a_dossier_expires(self):
        self.run_job()
        self.run_job()

        warning = self.warnings()
        self.assertEqual(len(warning), 1)
        self.assertIn("expires on", warning.body)
        self.assertIn(self.administrator.partner_id, warning.notification_ids.res_partner_id)

    def test_administrators_are_warned_again_on_the_last_valid_day(self):
        self.run_job()
        self.registration.valid_until = self.today

        self.run_job()

        self.assertEqual(len(self.warnings()), 2)
        self.assertIn("expires today", self.warnings()[:1].body)

    def test_no_warning_comes_before_the_warning_days_or_after_the_dossier_expired(self):
        for valid_until in (self.today + timedelta(days=8), self.today - timedelta(days=1)):
            self.registration.valid_until = valid_until
            self.run_job()

        self.assertFalse(self.warnings())

    def test_an_archived_dossier_is_not_warned(self):
        self.registration.active = False

        self.run_job()

        self.assertFalse(self.warnings())

    def test_a_renewed_dossier_is_warned_before_its_new_expiry(self):
        self.run_job()
        self.registration.valid_until = self.today + timedelta(days=5)

        self.run_job()

        self.assertEqual(len(self.warnings()), 2)
