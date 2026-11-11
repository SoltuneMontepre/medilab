from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_SAMPLE_TYPE,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

LINE_TABLE = "medilab_accreditation_scope_line"


@tagged("post_install", "-at_install")
class TestAccreditationCertificate(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE]
        cls.today = cls.Certificate._laboratory_today()
        cls.sample_type = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled drinking water"})
        cls.certificate = cls.Certificate.create(
            {
                "code": "VILAS-FK",
                "valid_from": cls.today - timedelta(days=1),
                "valid_until": cls.today + timedelta(days=30),
                "scope_line_ids": [cls.scope_line(cls.method, cls.parameter, cls.sample_type)],
            }
        )

    def foreign_keys(self, table):
        self.env.cr.execute(
            """
            SELECT a.attname, pg_get_constraintdef(c.oid)
              FROM pg_constraint c
              JOIN pg_class t ON c.conrelid = t.oid
              JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1]
             WHERE t.relname = %s AND c.contype = 'f'
             ORDER BY a.attname
            """,
            [table],
        )
        return dict(self.env.cr.fetchall())

    def test_scope_line_foreign_keys(self):
        fks = self.foreign_keys(LINE_TABLE)
        self.assertIn("ON DELETE CASCADE", fks["certificate_id"])
        self.assertIn("ON DELETE RESTRICT", fks["method_id"])
        self.assertIn("ON DELETE RESTRICT", self.foreign_keys(f"{LINE_TABLE}_parameter_rel")["parameter_id"])
        self.assertIn("ON DELETE RESTRICT", self.foreign_keys(f"{LINE_TABLE}_sample_type_rel")["sample_type_id"])

    def test_deleting_certificate_deletes_its_lines_and_keeps_methods(self):
        line_id = persisted_id(self.certificate.scope_line_ids)
        self.certificate.unlink()
        self.assertFalse(self.env[MODEL_ACCREDITATION_SCOPE_LINE].browse(line_id).exists())
        self.assertTrue(self.method.exists())

    def test_deleting_method_still_in_a_scope_is_refused(self):
        with self.assertRaises(UserError), mute_logger("odoo.sql_db"):
            self.method.unlink()

    def test_multiple_certificates_can_cover_the_same_method(self):
        second = self.Certificate.create(
            {"code": "VILAS-FK-2", "scope_line_ids": [self.scope_line(self.method, self.parameter, self.sample_type)]}
        )
        self.assertEqual(self.method.certificate_ids, self.certificate | second)

    def test_certificate_lists_the_methods_of_its_lines(self):
        other = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6187-1:2009", "name": "E. coli", "field_id": self.testing_field.id}
        )
        self.certificate.scope_line_ids = [self.scope_line(other, self.parameter, self.sample_type)]
        self.assertEqual(self.certificate.method_ids, self.method | other)
        self.assertEqual(self.Certificate.search([("method_ids", "in", other.ids)]), self.certificate)

    def test_line_without_parameter_or_sample_type_is_refused(self):
        for vals in (
            {"parameter_ids": [Command.clear()]},
            {"sample_type_ids": [Command.clear()]},
        ):
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                self.certificate.scope_line_ids.write(vals)
        with self.assertRaises(ValidationError):
            self.env[MODEL_ACCREDITATION_SCOPE_LINE].create(
                {"certificate_id": self.certificate.id, "method_id": self.method.id}
            )

    def test_complete_line_is_not_to_confirm(self):
        self.assertFalse(self.certificate.scope_line_ids.to_confirm)
