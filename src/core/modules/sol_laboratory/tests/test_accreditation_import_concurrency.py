import threading
import uuid
from unittest.mock import patch

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.fields import Command
from odoo.http.retrying import retrying
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestAccreditationImportConcurrency(MasterDataCase):
    """Two real database transactions through Odoo 20 request retrying."""

    def test_two_transactions_import_the_same_method_code(self):
        """Concurrent create raises ConcurrencyError; retrying() completes one method and links."""
        code = f"CONC-2TXN-{uuid.uuid4().hex[:12]}"
        certificate_id, field_id = self._prepare_committed()
        self.addCleanup(self._remove_committed, certificate_id, field_id, [code, f"{code}-OTHER"])
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

    def _remove_committed(self, certificate_id, field_id, codes):
        # Deleting the certificate also removes the wizard and its lines, and frees the methods.
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {"active_test": False})
            env[MODEL_ACCREDITATION_CERTIFICATE].browse(certificate_id).unlink()
            env[MODEL_TESTING_METHOD].search([("code", "in", codes)]).unlink()
            env[MODEL_TESTING_FIELD].browse(field_id).unlink()
