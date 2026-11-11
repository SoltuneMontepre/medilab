from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestAccreditationSecurity(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE].create({"code": "VILAS-SEC"})
        cls.editor = new_test_user(
            cls.env,
            login="acc.cert.editor",
            groups="base.group_user,sol_laboratory.group_permission_accreditation_certificate_edit_all,"
            "sol_laboratory.group_permission_accreditation_scope_line_create_all",
        )
        cls.method_editor = new_test_user(
            cls.env,
            login="acc.method.editor",
            groups="base.group_user,sol_laboratory.group_permission_testing_method_edit_all",
        )
        cls.sales = new_test_user(cls.env, login="acc.sales", groups="base.group_user")

    def test_method_editor_cannot_mutate_certificate_ids(self):
        method = self.method.with_user(self.method_editor)
        for commands in (
            [Command.link(persisted_id(self.certificate))],
            [Command.unlink(persisted_id(self.certificate))],
            [Command.clear()],
            [Command.set([persisted_id(self.certificate)])],
        ):
            with self.subTest(commands=commands):
                with self.assertRaises(UserError):
                    method.write({"certificate_ids": commands})

    def test_method_create_with_certificate_ids_is_refused(self):
        with self.assertRaises(UserError):
            self.env[MODEL_TESTING_METHOD].with_user(self.method_editor).create(
                {
                    "code": "SEC-NEW",
                    "name": "Secured",
                    "field_id": self.testing_field.id,
                    "certificate_ids": [Command.link(persisted_id(self.certificate))],
                }
            )

    def test_sales_user_cannot_edit_certificate_scope(self):
        with self.assertRaises((AccessError, UserError)):
            self.certificate.with_user(self.sales).write(
                {"scope_line_ids": [self.scope_line(self.method, self.parameter, self.sample_type)]}
            )

    def test_certificate_editor_can_add_scope_lines(self):
        self.certificate.with_user(self.editor).write(
            {"scope_line_ids": [self.scope_line(self.method, self.parameter, self.sample_type)]}
        )
        self.assertEqual(self.certificate.method_ids, self.method)

    def test_certificate_scope_change_is_audited(self):
        self.certificate.write({"scope_line_ids": [self.scope_line(self.method, self.parameter, self.sample_type)]})
        entries = self.env["medilab.audit.entry"].search(
            [("parent_model", "=", MODEL_ACCREDITATION_CERTIFICATE), ("parent_id", "=", self.certificate.id)]
        )
        self.assertEqual(set(entries.mapped("document_model")), {MODEL_ACCREDITATION_SCOPE_LINE})
        self.assertIn(self.certificate.scope_line_ids.id, entries.mapped("document_id"))

    def test_manual_is_accredited_on_an_applicability_is_refused(self):
        editor = new_test_user(
            self.env,
            login="acc.applicability.editor",
            groups="base.group_user,sol_laboratory.group_permission_parameter_method_sample_type_edit_all",
        )
        with self.assertRaises(UserError):
            self.applicability.with_user(editor).write({"is_accredited": True})
        with self.assertRaises(UserError):
            self.applicability.write({"is_accredited": True})

    def test_manual_is_accredited_on_a_sample_test_is_refused(self):
        editor = new_test_user(
            self.env,
            login="acc.test.editor",
            groups="base.group_user,sol_laboratory.group_permission_sample_test_edit_all",
        )
        with self.assertRaises(UserError):
            self.sample.test_ids.with_user(editor).write({"is_accredited": True})
