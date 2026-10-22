from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_KEY_SCOPE,
    DEVICE_REVOKED,
    INVALID_CREDENTIALS,
    INVALID_KEY,
    INVALID_REQUEST,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_LABORATORY_DEVICE,
    MODEL_RES_USERS,
    MODEL_RES_USERS_APIKEYS,
)


@tagged("post_install", "-at_install")
class TestLaboratoryApiSignIn(LaboratoryApiCase):
    def device(self, client_uid):
        return self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", client_uid)])

    def test_signing_in_gives_the_computer_its_own_key(self):
        first = self.api_sign_in(self.tester, "first-installation").json()
        second = self.api_sign_in(self.tester, "second-installation", name="AAS-PC", platform="linux").json()

        self.assertNotEqual(first["key"], second["key"])
        self.assertEqual(first["device"]["id"], self.device("first-installation").id)
        self.assertEqual(
            {key: second["device"][key] for key in ("name", "platform", "status", "current")},
            {"name": "AAS-PC", "platform": "linux", "status": "signed_in", "current": True},
        )
        listed = self.api("GET", "/devices", key=first["key"]).json()["devices"]
        self.assertEqual([device["id"] for device in listed if device["current"]], [first["device"]["id"]])

    def test_signing_in_keeps_neither_the_password_nor_the_key(self):
        key = self.signed_in_key(self.tester, "installation")
        self.api_sign_in(self.tester, "installation", password="wrong")
        device = self.device("installation")
        self.env.cr.execute("SELECT key FROM res_users_apikeys WHERE id = %s", [device.api_key_id.id])
        [(hashed,)] = self.env.cr.fetchall()
        self.env.cr.execute("SELECT * FROM medilab_laboratory_sign_in_attempt")
        attempts = [str(value) for row in self.env.cr.fetchall() for value in row]
        entries = self.env[MODEL_AUDIT_ENTRY].search(
            [("document_model", "=", MODEL_LABORATORY_DEVICE), ("document_id", "=", device.id)]
        )
        kept = [str(value) for value in device.read()[0].values()] + attempts
        kept += entries.change_ids.mapped("old_value") + entries.change_ids.mapped("new_value")

        self.assertNotIn(key, hashed)
        for secret in (PASSWORD, "wrong", key):
            with self.subTest(secret=secret):
                self.assertFalse([value for value in kept if value and secret in value])

    def test_a_wrong_password_is_refused(self):
        self.assertApiRefused(INVALID_CREDENTIALS, self.api_sign_in(self.tester, "installation", password="wrong"))
        self.assertFalse(self.device("installation"))

    def test_a_computer_key_does_not_sign_another_computer_in(self):
        key = self.signed_in_key(self.tester, "installation")

        self.assertApiRefused(INVALID_CREDENTIALS, self.api_sign_in(self.tester, "other", password=key))

    def test_a_person_with_two_factor_authentication_signs_in_with_an_api_key(self):
        if "totp_secret" not in self.env[MODEL_RES_USERS]._fields:
            self.skipTest("Odoo's two-factor authentication is not installed.")
        self.tester.sudo().totp_secret = "JBSWY3DPEHPK3PXP"
        api_key = self.env[MODEL_RES_USERS_APIKEYS].with_user(self.tester).sudo()._generate("rpc", "Sign-in", None)

        self.assertApiRefused(INVALID_CREDENTIALS, self.api_sign_in(self.tester, "installation"))
        self.assertEqual(self.api_sign_in(self.tester, "installation", password=api_key).status_code, 200)

    def test_a_person_without_the_laboratory_files_permission_cannot_sign_in(self):
        self.assertApiRefused(PERMISSION_DENIED, self.api_sign_in(self.colleague, "installation"))
        self.assertFalse(self.device("installation"))

    def test_a_revoked_computer_cannot_sign_in_again(self):
        self.signed_in_key(self.tester, "installation")
        self.device("installation").with_user(self.tester).action_revoke()

        self.assertApiRefused(DEVICE_REVOKED, self.api_sign_in(self.tester, "installation"))

    def test_signing_in_again_keeps_one_computer_and_stops_its_old_key(self):
        old_key = self.signed_in_key(self.tester, "installation")
        new_key = self.signed_in_key(self.tester, "installation", name="HPLC-PC-2")

        self.assertEqual(len(self.device("installation")), 1)
        self.assertEqual(self.device("installation").name, "HPLC-PC-2")
        self.assertApiRefused(INVALID_KEY, self.api("GET", "/devices", key=old_key))
        self.assertEqual(self.api("GET", "/devices", key=new_key).status_code, 200)

    def test_a_computer_is_named_never_given_a_path(self):
        for field, value in (
            ("name", "C:\\Users\\lab"),
            ("name", "/home/lab"),
            ("name", "~lab"),
            ("name", ".."),
            ("client_uid", "C:\\Program Files\\Medilab Sync"),
            ("client_uid", "/opt/medilab-sync"),
        ):
            with self.subTest(field=field, value=value):
                values = {"client_uid": "installation", "name": "HPLC-PC", field: value}
                self.assertApiRefused(INVALID_REQUEST, self.api_sign_in(self.tester, **values))
        self.assertFalse(self.env[MODEL_LABORATORY_DEVICE].search([("user_id", "=", self.tester.id)]))

    def test_signing_out_stops_the_key_and_the_computer_signs_in_again(self):
        key = self.signed_in_key(self.tester, "installation")

        self.assertEqual(self.api("POST", "/sign-out", key=key).status_code, 204)
        # A repeated sign-out, such as one whose answer was lost, finds the key gone.
        self.assertApiRefused(INVALID_KEY, self.api("POST", "/sign-out", key=key))
        self.assertEqual(self.device("installation").status, "signed_out")
        self.assertIsNone(self.env[MODEL_RES_USERS_APIKEYS]._check_credentials(scope=DEVICE_KEY_SCOPE, key=key))
        again = self.api_sign_in(self.tester, "installation").json()
        self.assertEqual(again["device"]["id"], self.device("installation").id)
