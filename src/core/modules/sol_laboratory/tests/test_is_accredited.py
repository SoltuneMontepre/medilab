from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.fields import Command
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_METHOD,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestIsAccredited(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE]
        cls.today = cls.Certificate._laboratory_today()
        cls.certificate = cls.Certificate.create(
            {
                "code": "VILAS-A",
                "valid_from": cls.today - timedelta(days=10),
                "valid_until": cls.today + timedelta(days=10),
                "method_ids": [Command.set(cls.method.ids)],
            }
        )
        cls.subcontractor = cls.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Lab"})

    def test_in_house_pair_on_valid_certificate_is_accredited(self):
        self.assertTrue(self.pair.is_accredited)

    def test_subcontracted_pair_is_never_accredited(self):
        pair = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "subcontractor_id": self.subcontractor.id,
            }
        )
        self.assertFalse(pair.is_accredited)

    def test_day_after_valid_until_is_not_accredited(self):
        after = self.certificate.valid_until + timedelta(days=1)
        with (
            freeze_time(f"{after.isoformat()} 10:00:00"),
            patch.object(type(self.env.company), "tz", "Asia/Ho_Chi_Minh"),
        ):
            self.pair._recompute_is_accredited()
            self.assertFalse(self.pair.is_accredited)

    def test_first_valid_day_is_accredited(self):
        self.certificate.valid_from = self.today + timedelta(days=5)
        self.pair._recompute_is_accredited()
        self.assertFalse(self.pair.is_accredited)
        on_day = self.certificate.valid_from
        with freeze_time(f"{on_day.isoformat()} 10:00:00"):
            self.pair._recompute_is_accredited()
            self.assertTrue(self.pair.is_accredited)

    def test_open_ended_certificate_is_accredited(self):
        self.certificate.write({"valid_from": False, "valid_until": False})
        self.assertTrue(self.pair.is_accredited)

    def test_future_certificate_is_not_accredited_yet(self):
        self.certificate.write(
            {
                "valid_from": self.today + timedelta(days=30),
                "valid_until": self.today + timedelta(days=60),
            }
        )
        self.assertFalse(self.pair.is_accredited)

    def test_overlapping_certificates_keep_accreditation(self):
        self.env[MODEL_ACCREDITATION_CERTIFICATE].create(
            {
                "code": "VILAS-B",
                "valid_from": self.today - timedelta(days=1),
                "valid_until": self.today + timedelta(days=1),
                "method_ids": [Command.link(self.method.id)],
            }
        )
        self.certificate.valid_until = self.today - timedelta(days=1)
        self.assertTrue(self.pair.is_accredited)

    def test_unlinking_method_clears_accreditation(self):
        self.certificate.method_ids = [Command.unlink(self.method.id)]
        self.assertFalse(self.pair.is_accredited)

    def test_archiving_certificate_clears_accreditation_and_keeps_links(self):
        self.certificate.active = False
        self.assertFalse(self.pair.is_accredited)
        self.assertIn(self.method, self.certificate.with_context(active_test=False).method_ids)

    def test_restoring_certificate_restores_accreditation(self):
        self.certificate.active = False
        self.certificate.active = True
        self.assertTrue(self.pair.is_accredited)

    def test_no_certificates_clears_stale_true(self):
        self.certificate.unlink()
        self.assertFalse(self.pair.is_accredited)

    def test_changing_pair_method_recomputes(self):
        other = self.env[MODEL_TESTING_METHOD].create(
            {"code": "OTHER-1", "name": "Other", "field_id": self.testing_field.id}
        )
        self.pair.method_id = other
        self.assertFalse(self.pair.is_accredited)

    def test_certificate_edit_does_not_recompute_unrelated_pairs(self):
        other_method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "OTHER-1", "name": "Other", "field_id": self.testing_field.id}
        )
        other_pair = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": other_method.id,
                "department_id": self.department.id,
            }
        )
        # Stale True on an unrelated pair must not be cleared by editing this certificate's dates.
        self.env.cr.execute("UPDATE medilab_parameter_method SET is_accredited = TRUE WHERE id = %s", [other_pair.id])
        self.certificate.write({"valid_until": self.certificate._laboratory_today()})
        self.env.cr.execute("SELECT is_accredited FROM medilab_parameter_method WHERE id = %s", [other_pair.id])
        stale = self.env.cr.fetchone()
        if stale is None:
            self.fail("The unrelated pair has no row.")
        self.assertTrue(stale[0])
