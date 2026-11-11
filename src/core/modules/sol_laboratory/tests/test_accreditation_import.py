from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_SAMPLE_TYPE,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestAccreditationImport(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE].create({"code": "VILAS-IMP"})
        cls.sample_type = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Vegetables"})
        cls.Import = cls.env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT]
        cls.admin = new_test_user(
            cls.env,
            login="acc.import.admin",
            groups="base.group_user,sol_laboratory.group_role_administrator",
        )

    def row(self, code, title, parameters=None, sample_types=None):
        parameters = self.parameter if parameters is None else parameters
        sample_types = self.sample_type if sample_types is None else sample_types
        return Command.create(
            {
                "code": code,
                "name": title,
                "parameter_ids": [Command.set(persisted_ids(parameters))],
                "sample_type_ids": [Command.set(persisted_ids(sample_types))],
            }
        )

    def _wizard(self, lines, field=None, lang="en_US", certificate=None, user=None, rows=()):
        return self.Import.with_user(user or self.admin).create(
            {
                "certificate_id": (certificate or self.certificate).id,
                "field_id": (field or self.testing_field).id,
                "lang": lang,
                "line_ids": [self.row(code, title) for code, title in lines] + list(rows),
            }
        )

    def test_import_creates_missing_links_all_and_leaves_existing_unchanged(self):
        existing_codes = [f"EXIST-{i}" for i in range(5)]
        for code in existing_codes:
            self.env[MODEL_TESTING_METHOD].create(
                {
                    "code": code,
                    "name": f"Existing {code}",
                    "field_id": self.testing_field.id,
                }
            )
        other_field = self.env[MODEL_TESTING_FIELD].create({"code": "MB", "name": "Microbiology"})
        existing = self.env[MODEL_TESTING_METHOD].search([("code", "in", existing_codes)])
        existing_names = {method.code: method.name for method in existing}
        existing_fields = {method.code: method.field_id.id for method in existing}
        lines = [(code, f"Title {code}") for code in existing_codes]
        lines += [(f"NEW-{i}", f"New {i}") for i in range(25)]
        wizard = self._wizard(lines, field=other_field)
        wizard.action_import()

        linked = self.certificate.method_ids
        self.assertEqual(len(linked), 30)
        for code in existing_codes:
            method = existing.filtered(lambda m, c=code: m.code == c)
            self.assertEqual(method.name, existing_names[code])
            self.assertEqual(method.field_id.id, existing_fields[code])
        created = linked.filtered(lambda m: assert_instance(m.code, str).startswith("NEW-"))
        self.assertEqual(len(created), 25)
        self.assertTrue(all(method.field_id == other_field for method in created))

    def test_lines_name_their_parameters_and_sample_types(self):
        self._wizard([("LINE-1", "One")]).action_import()
        line = self.certificate.scope_line_ids
        self.assertEqual(line.method_id.code, "LINE-1")
        self.assertEqual(line.parameter_ids, self.parameter)
        self.assertEqual(line.sample_type_ids, self.sample_type)
        self.assertFalse(line.to_confirm)

    def test_blank_title_takes_the_code(self):
        self._wizard([("TCVN 7602:2007", "")]).action_import()
        method = self.env[MODEL_TESTING_METHOD].search([("code", "=", "TCVN 7602:2007")])
        self.assertEqual(method.name, "TCVN 7602:2007")

    def test_row_without_parameters_or_sample_types_refuses_entire_import(self):
        for row in (
            self.row("NO-PARAM", "No parameter", parameters=self.parameter.browse()),
            self.row("NO-TYPE", "No sample type", sample_types=self.sample_type.browse()),
        ):
            with self.subTest(row=row):
                wizard = self._wizard([("OK-1", "Ok")], rows=[row])
                with self.assertRaises(ValidationError):
                    wizard.action_import()
                codes = ["OK-1", "NO-PARAM", "NO-TYPE"]
                self.assertFalse(self.env[MODEL_TESTING_METHOD].search([("code", "in", codes)]))
                self.assertFalse(self.certificate.scope_line_ids)

    def test_a_code_on_several_rows_makes_one_method_and_a_line_per_row(self):
        cadmium = self.create_parameter("Cadmium (Cd)", self.group)
        wizard = self._wizard([("SAME-1", "Metals")], rows=[self.row("SAME-1", "", parameters=cadmium)])
        wizard.action_import()
        method = self.env[MODEL_TESTING_METHOD].search([("code", "=", "SAME-1")])
        self.assertEqual(method.name, "Metals")
        lines = self.certificate.scope_line_ids
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines.method_id, method)
        self.assertEqual(lines.parameter_ids, self.parameter | cadmium)

    def test_importing_a_line_again_adds_nothing(self):
        self._wizard([("AGAIN-1", "Again"), ("AGAIN-1", "Again")]).action_import()
        self._wizard([("AGAIN-1", "Again")]).action_import()
        self.assertEqual(len(self.certificate.scope_line_ids), 1)

    def test_blank_code_refuses_entire_import(self):
        before = self.env[MODEL_TESTING_METHOD].search_count([])
        wizard = self._wizard([("OK-1", "Ok"), ("", "Missing code")])
        with self.assertRaises(ValidationError):
            wizard.action_import()
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([]), before)
        self.assertFalse(self.certificate.scope_line_ids)

    def test_titles_use_selected_language(self):
        wizard = self._wizard([("LANG-1", "Tiêu đề")], lang="vi_VN")
        wizard.action_import()
        method = self.env[MODEL_TESTING_METHOD].search([("code", "=", "LANG-1")])
        self.assertEqual(method.with_context(lang="vi_VN").name, "Tiêu đề")

    def test_archived_existing_method_is_linked_unchanged(self):
        method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "ARCH-1", "name": "Archived", "field_id": self.testing_field.id, "active": False}
        )
        name = method.name
        wizard = self._wizard([("ARCH-1", "Should not overwrite")])
        wizard.action_import()
        linked = self.certificate.with_context(active_test=False).method_ids
        self.assertIn(method, linked)
        self.assertEqual(method.name, name)

    def test_missing_certificate_edit_is_refused(self):
        user = new_test_user(
            self.env,
            login="acc.import.noedit",
            groups="base.group_user,sol_laboratory.group_permission_testing_method_create_all",
        )
        wizard = self._wizard([("X-1", "X")], user=user)
        with self.assertRaises((AccessError, UserError)):
            wizard.action_import()

    def test_missing_method_create_is_refused(self):
        user = new_test_user(
            self.env,
            login="acc.import.nocreate",
            groups="base.group_user,sol_laboratory.group_permission_accreditation_certificate_edit_all,"
            "sol_laboratory.group_permission_accreditation_scope_line_create_all",
        )
        wizard = self._wizard([("NEED-CREATE", "New")], user=user)
        with self.assertRaises(AccessError):
            wizard.action_import()

    def test_missing_scope_line_create_is_refused(self):
        user = new_test_user(
            self.env,
            login="acc.import.nolines",
            groups="base.group_user,sol_laboratory.group_permission_accreditation_certificate_edit_all",
        )
        self.env[MODEL_TESTING_METHOD].create(
            {"code": "EXISTING", "name": "Existing", "field_id": self.testing_field.id}
        )
        wizard = self._wizard([("EXISTING", "Existing")], user=user)
        with self.assertRaises(AccessError):
            wizard.action_import()
        self.assertFalse(self.certificate.scope_line_ids)

    def test_failure_rolls_back_partial_creates(self):
        before_methods = self.env[MODEL_TESTING_METHOD].search_count([])
        wizard = self._wizard([("RB-1", "One"), ("", "Missing code"), ("RB-2", "Two")])
        with self.assertRaises(ValidationError):
            wizard.action_import()
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([]), before_methods)
        self.assertFalse(self.certificate.scope_line_ids)

    def test_import_is_atomic_when_link_refused(self):
        """Missing certificate-edit permission must not leave newly created methods or links."""
        user = new_test_user(
            self.env,
            login="acc.import.atomic",
            groups="base.group_user,sol_laboratory.group_permission_testing_method_create_all",
        )
        before = self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([])
        wizard = self._wizard([("ATOM-1", "Atomic")], user=user)
        with self.assertRaises((AccessError, UserError)):
            wizard.action_import()
        self.assertEqual(
            self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([]),
            before,
        )
        self.assertFalse(self.certificate.scope_line_ids)

    def test_link_failure_after_create_rolls_back_methods(self):
        """A failure during certificate linking after creates must leave no methods or links."""
        before = self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([])
        wizard = self._wizard([("LINK-FAIL-1", "One"), ("LINK-FAIL-2", "Two")])

        def boom(*args, **kwargs):
            raise UserError("link refused for test")

        with patch.object(type(self.certificate), "write", boom):
            with self.assertRaises(UserError):
                wizard.action_import()

        self.assertEqual(
            self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([]),
            before,
        )
        self.assertFalse(
            self.env[MODEL_TESTING_METHOD]
            .with_context(active_test=False)
            .search([("code", "in", ["LINK-FAIL-1", "LINK-FAIL-2"])])
        )
        self.assertFalse(self.certificate.scope_line_ids)

    def test_concurrent_create_of_same_code_uses_existing(self):
        """A unique violation on create recovers the row inserted by a concurrent create."""
        code = "CONC-RACE-1"
        real_create_method = type(self.Import)._create_method

        def race_create_method(wizard, code_arg, title):
            if code_arg != code:
                return real_create_method(wizard, code_arg, title)
            # Concurrent insert of the same code, then the real recovery path runs.
            self.env[MODEL_TESTING_METHOD].create(
                {
                    "code": code,
                    "name": "Winner",
                    "field_id": self.testing_field.id,
                }
            )
            with mute_logger("odoo.sql_db"):
                return real_create_method(wizard, code_arg, title)

        wizard = self._wizard([(code, "From import"), ("CONC-RACE-2", "Other")])
        with patch.object(type(self.Import), "_create_method", race_create_method):
            wizard.action_import()

        winner = self.env[MODEL_TESTING_METHOD].search([("code", "=", code)])
        self.assertEqual(winner.name, "Winner")
        linked = self.certificate.with_context(active_test=False).method_ids
        self.assertIn(winner, linked)
        self.assertTrue(linked.filtered(lambda method: method.code == "CONC-RACE-2"))
