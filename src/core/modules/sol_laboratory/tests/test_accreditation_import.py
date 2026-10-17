import threading
import uuid
from unittest.mock import patch

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.http.retrying import retrying
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestAccreditationImport(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE].create({"code": "VILAS-IMP"})
        cls.Import = cls.env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT]
        cls.admin = new_test_user(
            cls.env,
            login="acc.import.admin",
            groups="base.group_user,sol_laboratory.group_role_administrator",
        )

    def _wizard(self, lines, field=None, lang="en_US", certificate=None):
        return self.Import.with_user(self.admin).create(
            {
                "certificate_id": (certificate or self.certificate).id,
                "field_id": (field or self.testing_field).id,
                "lang": lang,
                "line_ids": [Command.create({"code": code, "name": title}) for code, title in lines],
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
        created = linked.filtered(lambda m: m.code.startswith("NEW-"))
        self.assertEqual(len(created), 25)
        self.assertTrue(all(method.field_id == other_field for method in created))

    def test_blank_code_or_title_refuses_entire_import(self):
        before = self.env[MODEL_TESTING_METHOD].search_count([])
        wizard = self._wizard([("OK-1", "Ok"), ("", "Missing code")])
        with self.assertRaises(ValidationError):
            wizard.action_import()
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([]), before)
        self.assertFalse(self.certificate.method_ids)

    def test_duplicate_codes_refuse_entire_import(self):
        before = self.env[MODEL_TESTING_METHOD].search_count([])
        wizard = self._wizard([("DUP-1", "One"), ("DUP-1", "Two")])
        with self.assertRaises(ValidationError):
            wizard.action_import()
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([]), before)
        self.assertFalse(self.certificate.method_ids)

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
        wizard = self.Import.with_user(user).create(
            {
                "certificate_id": self.certificate.id,
                "field_id": self.testing_field.id,
                "lang": "en_US",
                "line_ids": [Command.create({"code": "X-1", "name": "X"})],
            }
        )
        with self.assertRaises((AccessError, UserError)):
            wizard.action_import()

    def test_missing_method_create_is_refused(self):
        user = new_test_user(
            self.env,
            login="acc.import.nocreate",
            groups="base.group_user,sol_laboratory.group_permission_accreditation_certificate_edit_all",
        )
        wizard = self.Import.with_user(user).create(
            {
                "certificate_id": self.certificate.id,
                "field_id": self.testing_field.id,
                "lang": "en_US",
                "line_ids": [Command.create({"code": "NEED-CREATE", "name": "New"})],
            }
        )
        with self.assertRaises(AccessError):
            wizard.action_import()

    def test_failure_rolls_back_partial_creates(self):
        before_methods = self.env[MODEL_TESTING_METHOD].search_count([])
        wizard = self._wizard([("RB-1", "One"), ("", "Missing title"), ("RB-2", "Two")])
        with self.assertRaises(ValidationError):
            wizard.action_import()
        self.assertEqual(self.env[MODEL_TESTING_METHOD].search_count([]), before_methods)
        self.assertFalse(self.certificate.method_ids)

    def test_import_is_atomic_when_link_refused(self):
        """Missing certificate-edit permission must not leave newly created methods or links."""
        user = new_test_user(
            self.env,
            login="acc.import.atomic",
            groups="base.group_user,sol_laboratory.group_permission_testing_method_create_all",
        )
        before = self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([])
        wizard = self.Import.with_user(user).create(
            {
                "certificate_id": self.certificate.id,
                "field_id": self.testing_field.id,
                "lang": "en_US",
                "line_ids": [Command.create({"code": "ATOM-1", "name": "Atomic"})],
            }
        )
        with self.assertRaises((AccessError, UserError)):
            wizard.action_import()
        self.assertEqual(
            self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search_count([]),
            before,
        )
        self.assertFalse(self.certificate.method_ids)

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
            self.env[MODEL_TESTING_METHOD].with_context(active_test=False).search(
                [("code", "in", ["LINK-FAIL-1", "LINK-FAIL-2"])]
            )
        )
        self.assertFalse(self.certificate.method_ids)

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


@tagged("post_install", "-at_install")
class TestAccreditationImportConcurrency(MasterDataCase):
    """Two real database transactions through Odoo 20 request retrying."""

    def test_two_transactions_import_the_same_method_code(self):
        """Concurrent create raises ConcurrencyError; retrying() completes one method and links."""
        code = f"CONC-2TXN-{uuid.uuid4().hex[:12]}"
        certificate_id, field_id = self._prepare_committed()
        wizard_id = self._commit_wizard(certificate_id, field_id, code)

        ready = threading.Event()
        committed = threading.Event()
        errors: list[Exception] = []
        create_attempts = {"n": 0}

        def winner() -> None:
            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    if not ready.wait(timeout=10):
                        errors.append(TimeoutError("importer never reached create"))
                        return
                    cursor.execute(
                        """
                        INSERT INTO medilab_testing_method
                            (code, name, field_id, active, create_uid, write_uid, create_date, write_date)
                        VALUES (
                            %s, %s::jsonb, %s, TRUE, %s, %s,
                            NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
                        )
                        """,
                        (code, '{"en_US": "Winner"}', field_id, SUPERUSER_ID, SUPERUSER_ID),
                    )
            except Exception as error:
                errors.append(error)
            finally:
                committed.set()

        thread = threading.Thread(target=winner)
        thread.start()
        try:
            with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                env = api.Environment(cursor, SUPERUSER_ID, {})
                real_create = type(env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT])._create_method

                def race_create(wiz, code_arg, title):
                    if code_arg != code:
                        return real_create(wiz, code_arg, title)
                    create_attempts["n"] += 1
                    if create_attempts["n"] == 1:
                        ready.set()
                        self.assertTrue(committed.wait(timeout=10), "winner never committed")
                        with mute_logger("odoo.sql_db"):
                            return real_create(wiz, code_arg, title)
                    return real_create(wiz, code_arg, title)

                def run_import():
                    return env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT].browse(wizard_id).action_import()

                with patch.object(
                    type(env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT]),
                    "_create_method",
                    race_create,
                ):
                    with mute_logger("odoo.sql_db", "odoo.http"):
                        retrying(run_import, env)
        finally:
            thread.join(15)
            self.assertFalse(thread.is_alive())

        self.assertFalse(errors, errors)
        self.assertEqual(create_attempts["n"], 1)

        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {})
            methods = env[MODEL_TESTING_METHOD].with_context(active_test=False).search([("code", "=", code)])
            self.assertEqual(len(methods), 1)
            self.assertEqual(methods.name, "Winner")
            certificate = env[MODEL_ACCREDITATION_CERTIFICATE].browse(certificate_id)
            linked = certificate.with_context(active_test=False).method_ids
            self.assertIn(methods.id, linked.ids)
            self.assertTrue(linked.filtered(lambda method: method.code == f"{code}-OTHER"))

    def _prepare_committed(self):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {})
            field = env[MODEL_TESTING_FIELD].create(
                {"code": f"F{uuid.uuid4().hex[:6]}", "name": "Concurrency field"}
            )
            certificate = env[MODEL_ACCREDITATION_CERTIFICATE].create(
                {"code": f"VILAS-{uuid.uuid4().hex[:8]}"}
            )
            return certificate.id, field.id

    def _commit_wizard(self, certificate_id, field_id, code):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {})
            wizard = env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT].create(
                {
                    "certificate_id": certificate_id,
                    "field_id": field_id,
                    "lang": "en_US",
                    "line_ids": [
                        Command.create({"code": code, "name": "From import"}),
                        Command.create({"code": f"{code}-OTHER", "name": "Other"}),
                    ],
                }
            )
            return wizard.id
