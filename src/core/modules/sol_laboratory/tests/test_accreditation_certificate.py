from datetime import timedelta

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_TESTING_METHOD,
)

REL = "medilab_accreditation_certificate_method_rel"


@tagged("post_install", "-at_install")
class TestAccreditationCertificate(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE]
        cls.today = cls.Certificate._laboratory_today()
        cls.certificate = cls.Certificate.create(
            {
                "code": "VILAS-FK",
                "valid_from": cls.today - timedelta(days=1),
                "valid_until": cls.today + timedelta(days=30),
                "method_ids": [Command.set(cls.method.ids)],
            }
        )

    def test_relation_foreign_keys(self):
        self.env.cr.execute(
            """
            SELECT a.attname, pg_get_constraintdef(c.oid)
              FROM pg_constraint c
              JOIN pg_class t ON c.conrelid = t.oid
              JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1]
             WHERE t.relname = %s AND c.contype = 'f'
             ORDER BY a.attname
            """,
            [REL],
        )
        fks = dict(self.env.cr.fetchall())
        self.assertIn("certificate_id", fks)
        self.assertIn("method_id", fks)
        self.assertIn("ON DELETE CASCADE", fks["certificate_id"])
        self.assertIn("ON DELETE RESTRICT", fks["method_id"])

    def test_deleting_certificate_does_not_delete_methods(self):
        method_id = self.method.id
        self.certificate.unlink()
        self.assertTrue(self.env[MODEL_TESTING_METHOD].browse(method_id).exists())

    def test_deleting_method_still_on_certificate_is_refused(self):
        with self.assertRaises(UserError), mute_logger("odoo.sql_db"):
            self.method.unlink()

    def test_multiple_certificates_can_cover_the_same_method(self):
        second = self.Certificate.create({"code": "VILAS-FK-2", "method_ids": [Command.link(self.method.id)]})
        self.assertEqual(self.method.certificate_ids, self.certificate | second)

    def test_expired_active_certificate_does_not_confer_accreditation(self):
        self.certificate.write(
            {
                "valid_from": self.today - timedelta(days=30),
                "valid_until": self.today - timedelta(days=1),
            }
        )
        self.assertTrue(self.certificate.active)
        self.assertFalse(self.pair.is_accredited)
