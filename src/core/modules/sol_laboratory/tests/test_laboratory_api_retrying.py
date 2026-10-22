from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.exceptions import ConcurrencyError
from odoo.http import retrying
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_api import TRY_AGAIN_SECONDS
from odoo.addons.sol_laboratory.constants.laboratory_files import TRY_AGAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_LABORATORY_DEVICE,
    MODEL_RES_USERS_APIKEYS,
)


@tagged("post_install", "-at_install")
class TestLaboratoryApiRetrying(LaboratoryApiCase):
    """Odoo's request retrying inside real requests of the API: a route that fails on concurrency runs again from
    authenticating the key, and its work counts once."""

    def setUp(self):
        super().setUp()
        # Odoo waits a random time before each new try; these tests do not.
        self.patch(retrying, "random", SimpleNamespace(uniform=lambda _low, _high: 0))
        self.key = self.signed_in_key(self.tester, "first-installation")
        self.signed_in_key(self.tester, "second-installation")
        self.device = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "first-installation")])
        self.second = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "second-installation")])
        self.authentications = 0
        keys = type(self.env[MODEL_RES_USERS_APIKEYS])
        check_credentials = keys._check_credentials

        def count_authentications(apikeys, *, scope, key):
            self.authentications += 1
            return check_credentials(apikeys, scope=scope, key=key)

        self.patch(keys, "_check_credentials", count_authentications)

    def fail_on_concurrency(self, method_name, tries=1):
        """Make the device's method fail on concurrency on its first tries, as a concurrent request would; the number
        of times it ran is kept."""
        devices = type(self.env[MODEL_LABORATORY_DEVICE])
        method = getattr(devices, method_name)
        runs = []

        def failing(*args, **kwargs):
            runs.append(1)
            if len(runs) <= tries:
                raise ConcurrencyError("A concurrent request changed the same records.")
            return method(*args, **kwargs)

        self.patch(devices, method_name, failing)
        return runs

    def entries(self, device):
        return self.env[MODEL_AUDIT_ENTRY].search(
            [("document_model", "=", MODEL_LABORATORY_DEVICE), ("document_id", "=", device.id)]
        )

    def test_a_route_run_again_authenticates_again_and_answers_once(self):
        runs = self.fail_on_concurrency("_from_key")

        with mute_logger("odoo.http"):
            response = self.api("GET", "/devices", key=self.key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(runs), 2)
        self.assertEqual(self.authentications, 2)

    def test_signing_out_run_again_signs_out_once(self):
        entries = self.entries(self.device)
        runs = self.fail_on_concurrency("_sign_out")

        with mute_logger("odoo.http"):
            response = self.api("POST", "/sign-out", key=self.key)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(self.entries(self.device) - entries), 1)
        self.assertEqual(self.device.status, "signed_out")

    def test_revoking_run_again_revokes_once(self):
        entries = self.entries(self.second)
        runs = self.fail_on_concurrency("action_revoke")

        with mute_logger("odoo.http"):
            response = self.api("POST", f"/devices/{self.second.id}/revoke", key=self.key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(self.entries(self.second) - entries), 1)

    def test_signing_in_run_again_keeps_one_computer_and_one_key(self):
        runs = self.fail_on_concurrency("_create_signed_in")

        with mute_logger("odoo.http"):
            response = self.api_sign_in(self.tester, "third-installation", name="GC-PC")

        device = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "third-installation")])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(device), 1)
        self.assertEqual(len(self.entries(device)), 1)
        self.env.cr.execute("SELECT count(*) FROM res_users_apikeys WHERE name = 'Medilab Sync: GC-PC'")
        self.assertEqual(self.env.cr.fetchall(), [(1,)])

    def test_a_request_still_failing_after_odoos_last_try_is_answered_try_again(self):
        runs = self.fail_on_concurrency("action_revoke", tries=5)

        with mute_logger("odoo.http"):
            response = self.api("POST", f"/devices/{self.second.id}/revoke", key=self.key)

        self.assertApiRefused(TRY_AGAIN, response)
        self.assertEqual(response.headers["Retry-After"], str(TRY_AGAIN_SECONDS))
        self.assertEqual(len(runs), 5)
        self.assertEqual(self.second.status, "signed_in")

    def test_a_reading_route_that_records_the_computers_call_answers_once(self):
        self.device.sudo().last_seen_at = fields.Datetime.now() - timedelta(minutes=2)
        runs = self.fail_on_concurrency("_from_key", tries=0)

        with self.assertNoLogs("odoo.http", "WARNING"):
            response = self.api("GET", "/devices", key=self.key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(runs), 1)
        self.assertGreater(self.device.last_seen_at, fields.Datetime.now() - timedelta(minutes=1))
