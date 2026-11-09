from odoo.tests import new_test_user, tagged

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_REVOKED,
    INVALID_CREDENTIALS,
    INVALID_KEY,
    INVALID_REQUEST,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_MODULE_MODULE,
    MODEL_LABORATORY_DEVICE,
    MODEL_MOBILE_DEVICE,
)


@tagged("post_install", "-at_install")
class TestMedilabMobileSignIn(LaboratoryApiCase):
    """Phones sign in on Medilab Mobile through the laboratory files API, for any internal user, and their push tokens
    stop with their keys."""

    def phone_key(self, user, client_uid="phone", name="Pixel 8"):
        return self.signed_in_key(user, client_uid, name=name, platform="android")

    def phone(self, client_uid="phone"):
        return self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", client_uid)])

    def token_of(self, phone):
        return (
            self.env[MODEL_MOBILE_DEVICE]
            .with_context(active_test=False)
            .search([("laboratory_device_id", "=", phone.id)])
        )

    def register(self, key, token="fcm-token"):
        return self.api("PUT", "/push-token", {"token": token}, key=key)

    def test_a_person_of_the_laboratory_signs_a_phone_in_without_the_laboratory_files_permission(self):
        response = self.api_sign_in(self.colleague, "phone", name="Pixel 8", platform="android")

        self.assertEqual(response.status_code, 200, response.text)
        device = response.json()["device"]
        self.assertEqual((device["platform"], device["status"]), ("android", "signed_in"))
        self.assertEqual(self.phone().api_key_id.sudo().name, "Medilab Mobile: Pixel 8")

    def test_a_computer_still_needs_the_laboratory_files_permission(self):
        self.assertApiRefused(PERMISSION_DENIED, self.api_sign_in(self.colleague, "computer", platform="linux"))

    def test_a_portal_user_cannot_sign_a_phone_in(self):
        portal = new_test_user(self.env, login="lab.customer", password=PASSWORD, groups="base.group_portal")

        self.assertApiRefused(PERMISSION_DENIED, self.api_sign_in(portal, "phone", platform="android"))
        self.assertFalse(self.phone())

    def test_a_revoked_phone_is_refused_at_its_next_call_and_its_token_is_turned_off(self):
        key = self.phone_key(self.tester)
        self.register(key)

        self.phone().with_user(self.administrator).action_revoke()

        self.assertApiRefused(INVALID_KEY, self.api("GET", "/modules", key=key))
        self.assertFalse(self.token_of(self.phone()).active)
        self.assertApiRefused(DEVICE_REVOKED, self.api_sign_in(self.tester, "phone", platform="android"))

    def test_an_archived_person_is_refused_at_the_next_call(self):
        key = self.phone_key(self.colleague)

        self.colleague.sudo().active = False

        self.assertApiRefused(INVALID_KEY, self.api("GET", "/modules", key=key))

    def test_signing_out_turns_the_push_token_off(self):
        key = self.phone_key(self.colleague)
        self.assertEqual(self.register(key).status_code, 204)
        token = self.token_of(self.phone())
        self.assertTrue(token.active)

        self.assertEqual(self.api("POST", "/sign-out", key=key).status_code, 204)

        self.assertFalse(token.active)
        self.assertEqual(self.phone().status, "signed_out")

    def test_removing_the_phone_key_from_anywhere_turns_its_token_off(self):
        key = self.phone_key(self.colleague)
        self.register(key)

        self.phone().api_key_id.sudo()._remove()

        self.assertFalse(self.token_of(self.phone()).active)

    def test_signing_in_again_keeps_the_token_until_the_app_registers_it_again(self):
        key = self.phone_key(self.colleague)
        self.register(key, "first-token")

        key = self.phone_key(self.colleague)
        self.register(key, "second-token")

        token = self.token_of(self.phone())
        self.assertEqual((token.token, token.active), ("second-token", True))

    def test_a_token_registered_for_another_phone_moves_to_this_one(self):
        first = self.phone_key(self.colleague, "first-phone")
        second = self.phone_key(self.colleague, "second-phone")
        self.register(first, "shared-token")

        self.register(second, "shared-token")

        tokens = self.env[MODEL_MOBILE_DEVICE].with_context(active_test=False).search([("token", "=", "shared-token")])
        self.assertEqual(tokens.laboratory_device_id, self.phone("second-phone"))
        self.assertFalse(self.token_of(self.phone("first-phone")))

    def test_unregistering_turns_the_token_off_once(self):
        key = self.phone_key(self.colleague)
        self.register(key)

        self.assertEqual(self.api("DELETE", "/push-token", key=key).status_code, 204)
        self.assertEqual(self.api("DELETE", "/push-token", key=key).status_code, 204)

        self.assertFalse(self.token_of(self.phone()).active)
        self.assertEqual(self.phone().status, "signed_in")

    def test_a_computer_has_no_push_token(self):
        key = self.signed_in_key(self.tester, "computer")

        self.assertApiRefused(INVALID_REQUEST, self.register(key))
        self.assertApiRefused(INVALID_REQUEST, self.api("DELETE", "/push-token", key=key))

    def test_a_token_is_registered_only_with_a_key(self):
        self.authenticate(self.colleague.login, PASSWORD)

        self.assertApiRefused(INVALID_KEY, self.register(None))
        self.assertFalse(self.env[MODEL_MOBILE_DEVICE].search([("token", "=", "fcm-token")]))

    def test_the_modules_are_the_installed_medilab_modules(self):
        key = self.phone_key(self.colleague)

        modules = self.api("GET", "/modules", key=key).json()["modules"]

        installed = self.env[MODEL_IR_MODULE_MODULE].search([("state", "=", "installed"), ("name", "=like", "sol\\_%")])
        self.assertEqual(modules, sorted(installed.mapped("name")))
        self.assertIn("sol_laboratory", modules)
        self.assertNotIn("base", modules)

    def test_the_answer_is_in_the_language_the_app_asks_for(self):
        self.colleague.lang = "en_US"
        body = {"login": self.colleague.login, "password": "wrong", "client_uid": "phone", "name": "Pixel 8"}
        body["platform"] = "android"

        for language, message in (
            ("vi", "Tên đăng nhập hoặc mật khẩu không đúng."),
            ("en", "The login or the password is wrong."),
            ("fr", "The login or the password is wrong."),
        ):
            with self.subTest(language=language):
                response = self.api("POST", "/sign-in", body, headers={"Accept-Language": language})
                self.assertApiRefused(INVALID_CREDENTIALS, response)
                self.assertEqual(response.json()["error"]["message"], message)

    def test_a_key_odoo_refuses_is_answered_in_the_language_the_app_asks_for(self):
        response = self.api("GET", "/modules", key="not-a-key", headers={"Accept-Language": "vi"})

        self.assertApiRefused(INVALID_KEY, response)
        self.assertEqual(response.json()["error"]["message"], "Thiết bị này chưa đăng nhập.")
