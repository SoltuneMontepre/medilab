from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_METHOD,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestAccreditationSecurity(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE].create({"code": "VILAS-SEC"})
        cls.editor = new_test_user(
            cls.env,
            login="acc.cert.editor",
            groups="base.group_user,sol_laboratory.group_permission_accreditation_certificate_edit_all",
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
            [Command.link(self.certificate.id)],
            [Command.unlink(self.certificate.id)],
            [Command.clear()],
            [Command.set([self.certificate.id])],
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
                    "certificate_ids": [Command.link(self.certificate.id)],
                }
            )

    def test_sales_user_cannot_edit_certificate_scope(self):
        with self.assertRaises((AccessError, UserError)):
            self.certificate.with_user(self.sales).write({"method_ids": [Command.link(self.method.id)]})

    def test_certificate_editor_can_link_methods(self):
        self.certificate.with_user(self.editor).write({"method_ids": [Command.link(self.method.id)]})
        self.assertIn(self.method, self.certificate.method_ids)

    def test_certificate_scope_change_is_audited(self):
        Audit = self.env["medilab.audit.entry"]
        before = Audit.search_count(
            [("document_model", "=", MODEL_ACCREDITATION_CERTIFICATE), ("document_id", "=", self.certificate.id)]
        )
        self.certificate.write({"method_ids": [Command.link(self.method.id)]})
        after = Audit.search_count(
            [("document_model", "=", MODEL_ACCREDITATION_CERTIFICATE), ("document_id", "=", self.certificate.id)]
        )
        self.assertGreater(after, before)

    def test_manual_is_accredited_write_is_refused(self):
        editor = new_test_user(
            self.env,
            login="acc.pair.editor",
            groups="base.group_user,sol_laboratory.group_permission_parameter_method_edit_all",
        )
        pair = self.pair.with_user(editor)
        with self.assertRaises(UserError):
            pair.write({"is_accredited": True})

    def test_manual_is_accredited_create_is_refused(self):
        method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "SEC-ACC", "name": "Sec Acc", "field_id": self.testing_field.id}
        )
        with self.assertRaises(UserError):
            self.env[MODEL_PARAMETER_METHOD].create(
                {
                    "parameter_id": self.parameter.id,
                    "method_id": method.id,
                    "unit_id": self.unit.id,
                    "department_id": self.department.id,
                    "is_accredited": True,
                }
            )

    def test_manual_is_accredited_on_subcontracted_and_expired_is_refused(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create({"name": "Sec Sub"})
        subcontracted = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": subcontractor.id,
            }
        )
        with self.assertRaises(UserError):
            subcontracted.write({"is_accredited": True})
        self.certificate.write({"method_ids": [Command.link(self.method.id)]})
        from datetime import timedelta

        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        self.certificate.write({"valid_until": today - timedelta(days=1)})
        self.pair.invalidate_recordset(["is_accredited"])
        self.assertFalse(self.pair.is_accredited)
        with self.assertRaises(UserError):
            self.pair.write({"is_accredited": True})
