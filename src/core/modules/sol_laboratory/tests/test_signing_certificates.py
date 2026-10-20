import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from .signing_case import ACCOUNT, CREDENTIAL, FakeViettelSign, self_signed
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB, MODEL_SIGNING_CERTIFICATE
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.constants.signing import CERTIFICATE_REVOKED, SIGNING_CERTIFICATES_JOB
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_PERSON
from odoo.addons.sol_laboratory.services.viettel_sign_client import ViettelSignClient, ViettelSignError

ALERT_EVENT = "sol_laboratory.event_signing_certificate_alert"


@tagged("post_install", "-at_install")
class TestSigningCertificates(TransactionCase):
    """The laboratory's certificate is read from Viettel Sign, which reports it valid for 20 days."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key, cls.der = self_signed("Phong Thu Nghiem An Phu", 20)
        cls.certificates = cls.env[MODEL_SIGNING_CERTIFICATE]
        cls.administrator = cls.env.ref(ADMINISTRATOR_PERSON).user_id
        # A mandatory alert reaches an administrator by email.
        cls.administrator.partner_id.email = "admin@anphu.example"

    def setUp(self):
        super().setUp()
        self.viettel = FakeViettelSign(self.key, self.der)
        viettel = self.viettel
        self.patch(
            ViettelSignClient,
            "_post",
            lambda client, path, payload, token=None: viettel.post(client, path, payload, token),
        )
        self.startPatcher(patch.dict(os.environ, ACCOUNT))
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, False)
        # Certificates the database already holds, such as the demo data's, take no part in these alerts.
        self.certificates.search([]).write({"status": CERTIFICATE_REVOKED})

    def alerts(self, certificate):
        return self.env["mail.message"].search(
            [
                ("model", "=", certificate._name),
                ("res_id", "=", certificate.id),
                ("subtype_id", "=", self.env.ref(ALERT_EVENT).id),
            ]
        )

    def test_refreshing_stores_the_certificate_and_its_expiry_as_viettel_sign_reports_it(self):
        self.certificates._refresh()

        certificate = self.certificates.search([("credential_id", "=", CREDENTIAL)])
        self.assertEqual(certificate.name, "Phong Thu Nghiem An Phu")
        self.assertEqual(certificate.status, "valid")
        self.assertAlmostEqual(
            certificate.valid_to, fields.Datetime.now() + timedelta(days=20), delta=timedelta(minutes=5)
        )
        self.assertTrue(certificate.checked_at)
        self.assertTrue(certificate.certificate_chain.startswith("-----BEGIN CERTIFICATE-----"))
        self.assertNotIn(ACCOUNT["VIETTEL_SIGN_CLIENT_SECRET"], str(certificate.read()))

        self.viettel.certificate_status = "revoked"
        self.certificates._refresh()

        self.assertEqual(certificate.status, "revoked")
        self.assertEqual(self.certificates.search_count([("credential_id", "=", CREDENTIAL)]), 1)

    def test_a_disabled_key_makes_the_certificate_revoked(self):
        self.viettel.key_status = "DISABLED"

        self.certificates._refresh()

        self.assertEqual(self.certificates.search([("credential_id", "=", CREDENTIAL)]).status, "revoked")

    def test_an_account_not_configured_cannot_be_read(self):
        with patch.dict(os.environ, {"VIETTEL_SIGN_CLIENT_SECRET": ""}), self.assertRaises(ViettelSignError):
            self.certificates._refresh()

    def test_only_administrators_refresh_the_certificates(self):
        clerk = new_test_user(self.env, "clerk.sign", groups="base.group_user")

        with self.assertRaises(AccessError):
            self.certificates.with_user(clerk).action_refresh()
        self.certificates.with_user(self.administrator).action_refresh()

        self.assertTrue(self.certificates.search([("credential_id", "=", CREDENTIAL)]))

    def test_administrators_are_alerted_once_before_the_certificate_expires(self):
        self.certificates._refresh()
        certificate = self.certificates.search([("credential_id", "=", CREDENTIAL)])

        self.certificates._alert()
        self.certificates._alert()

        alert = self.alerts(certificate)
        self.assertEqual(len(alert), 1)
        self.assertIn(self.administrator.partner_id, alert.notification_ids.res_partner_id)

    def test_no_expiry_alert_comes_while_the_certificate_is_far_from_its_end(self):
        self.env["ir.config_parameter"].set_int("sol_laboratory.signing_certificate_alert_days", 7)
        self.certificates._refresh()

        self.certificates._alert()

        self.assertFalse(self.alerts(self.certificates.search([("credential_id", "=", CREDENTIAL)])))

    def test_administrators_are_alerted_when_the_certificate_expires_and_when_it_is_revoked(self):
        self.certificates._refresh()
        certificate = self.certificates.search([("credential_id", "=", CREDENTIAL)])
        certificate.valid_to = fields.Datetime.now() - timedelta(hours=1)

        self.certificates._alert()

        self.assertEqual(certificate.status, "expired")
        self.assertIn("expired", self.alerts(certificate)[:1].body)

        certificate.status = "revoked"
        self.certificates._alert()

        self.assertIn("revoked", self.alerts(certificate)[:1].body)

    def test_a_renewed_certificate_silences_the_expiry_alert_of_the_old_one(self):
        self.certificates._refresh()
        old = self.certificates.search([("credential_id", "=", CREDENTIAL)])
        self.certificates.create(
            {
                **{field: old[field] for field in ("name", "certificate_chain")},
                "credential_id": "renewed",
                "fingerprint": "renewed",
                "valid_to": fields.Datetime.now() + timedelta(days=400),
            }
        )

        self.certificates._alert()

        self.assertFalse(self.alerts(old))

    def test_the_daily_job_alerts_and_refreshes_the_certificates_while_digital_signing_is_on(self):
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(SIGNING_CERTIFICATES_JOB)

        job._run_batch()
        self.assertFalse(self.certificates.search([("credential_id", "=", CREDENTIAL)]))

        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, True)
        job._run_batch()

        certificate = self.certificates.search([("credential_id", "=", CREDENTIAL)])
        self.assertEqual(certificate.status, "valid")
        self.assertEqual(len(self.alerts(certificate)), 1)
