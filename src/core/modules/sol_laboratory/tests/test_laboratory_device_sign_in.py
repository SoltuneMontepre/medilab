from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .laboratory_files_case import PASSWORD, LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_KEY_SCOPE,
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
class TestLaboratoryDeviceSignIn(LaboratoryFilesCase):
    def test_signing_in_gives_each_computer_its_own_key(self):
        first, first_key = self.sign_in(self.tester, "first-installation")
        second, second_key = self.sign_in(self.tester, "second-installation")

        self.assertNotEqual(first, second)
        self.assertNotEqual(first_key, second_key)
        self.assertEqual(self.device_of(first_key), first)
        self.assertEqual(self.device_of(second_key), second)
        self.assertEqual((first | second).mapped("status"), ["signed_in", "signed_in"])

    def test_signing_in_stores_neither_the_password_nor_the_key(self):
        device, key = self.sign_in(self.tester, "installation")
        self.env.flush_all()
        self.env.cr.execute("SELECT key, scope FROM res_users_apikeys WHERE id = %s", [device.api_key_id.id])
        [(hashed, scope)] = self.env.cr.fetchall()
        entries = self.env[MODEL_AUDIT_ENTRY].search(
            [("document_model", "=", MODEL_LABORATORY_DEVICE), ("document_id", "=", device.id)]
        )
        kept = [str(value) for value in device.read()[0].values()]
        kept += entries.change_ids.mapped("old_value") + entries.change_ids.mapped("new_value")

        self.assertEqual(scope, DEVICE_KEY_SCOPE)
        self.assertNotIn(key, hashed)
        for secret in (PASSWORD, key):
            with self.subTest(secret=secret):
                self.assertFalse([value for value in kept if value and secret in value])

    def test_a_computer_key_opens_only_the_laboratory_files(self):
        _device, key = self.sign_in(self.tester, "installation")
        keys = self.env[MODEL_RES_USERS_APIKEYS]

        self.assertEqual(keys._check_credentials(scope=DEVICE_KEY_SCOPE, key=key), self.tester.id)
        self.assertIsNone(keys._check_credentials(scope="rpc", key=key))

    def test_a_wrong_password_is_refused(self):
        devices = self.env[MODEL_LABORATORY_DEVICE]

        self.assertRefused(INVALID_CREDENTIALS, devices._sign_in, self.tester.login, "wrong", "pc", "HPLC-PC", "linux")

    def test_a_person_with_two_factor_authentication_signs_in_with_an_api_key(self):
        if "totp_secret" not in self.env[MODEL_RES_USERS]._fields:
            self.skipTest("Odoo's two-factor authentication is not installed.")
        self.tester.sudo().totp_secret = "JBSWY3DPEHPK3PXP"
        api_key = self.env[MODEL_RES_USERS_APIKEYS].with_user(self.tester).sudo()._generate("rpc", "Sign-in", None)
        devices = self.env[MODEL_LABORATORY_DEVICE]

        self.assertRefused(INVALID_CREDENTIALS, self.sign_in, self.tester, "installation")
        device, key = devices._sign_in(self.tester.login, api_key, "installation", "HPLC-PC", "windows")
        self.assertEqual(self.device_of(key), device)

    def test_a_computer_key_does_not_sign_another_computer_in(self):
        _device, key = self.sign_in(self.tester, "installation")
        devices = self.env[MODEL_LABORATORY_DEVICE]

        self.assertRefused(INVALID_CREDENTIALS, devices._sign_in, self.tester.login, key, "other", "AAS-PC", "linux")

    def test_a_person_without_the_laboratory_files_permission_cannot_sign_in(self):
        self.assertRefused(PERMISSION_DENIED, self.sign_in, self.colleague, "installation")
        self.assertFalse(self.env[MODEL_LABORATORY_DEVICE].search([("user_id", "=", self.colleague.id)]))

    def test_signing_in_again_replaces_the_key(self):
        device, old_key = self.sign_in(self.tester, "installation")
        again, new_key = self.sign_in(self.tester, "installation", name="HPLC-PC-2")

        self.assertEqual(again, device)
        self.assertEqual(device.name, "HPLC-PC-2")
        self.assertIsNone(self.env[MODEL_RES_USERS_APIKEYS]._check_credentials(scope=DEVICE_KEY_SCOPE, key=old_key))
        self.assertEqual(self.device_of(new_key), device)

    def test_signing_out_stops_the_key_and_keeps_the_computer(self):
        device, key = self.sign_in(self.tester, "installation")

        self.device_of(key)._sign_out()

        self.assertEqual(device.status, "signed_out")
        self.assertIsNone(self.env[MODEL_RES_USERS_APIKEYS]._check_credentials(scope=DEVICE_KEY_SCOPE, key=key))
        self.assertRefused(INVALID_KEY, device.with_user(self.tester)._from_key, key)
        _again, new_key = self.sign_in(self.tester, "installation")
        self.assertEqual(self.device_of(new_key), device)

    def test_a_computer_is_named_never_given_a_path(self):
        for name, platform in (("C:\\Users\\lab", "windows"), ("/home/lab", "linux"), ("HPLC-PC", "macos")):
            with self.subTest(name=name, platform=platform):
                self.assertRefused(INVALID_REQUEST, self.sign_in, self.tester, "installation", name, platform)

    def test_a_computer_records_its_calls_at_most_once_a_minute(self):
        device, key = self.sign_in(self.tester, "installation")
        recently = fields.Datetime.now() - timedelta(seconds=30)
        device.sudo().last_seen_at = recently

        self.device_of(key)
        self.assertEqual(device.last_seen_at, recently)

        device.sudo().last_seen_at = fields.Datetime.now() - timedelta(minutes=2)
        self.device_of(key)
        self.assertGreater(device.last_seen_at, recently)
