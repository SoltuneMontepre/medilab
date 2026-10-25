import os
import time
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from odoo.tests import BaseCase, tagged

from .editing_service import SECRET, callback
from odoo.addons.sol_laboratory.constants.laboratory_editing import JWT_SECRET_VARIABLE
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import EditingCallbackRefused, jwt_secret, sign, verify_callback

FIELDS = {"key": "Khirz6zTPdfd7", "status": 2, "url": "http://onlyoffice/output.xlsx", "users": ["7"]}


@tagged("post_install", "-at_install")
class TestOnlyofficeJwt(BaseCase):
    def assertRefused(self, body, header, secret=SECRET):
        with self.assertRaises(EditingCallbackRefused) as refusal:
            verify_callback(body, header, secret)
        # A refusal never repeats a token or the secret.
        self.assertNotIn(SECRET, str(refusal.exception))
        self.assertNotIn("eyJ", str(refusal.exception))

    def test_a_callback_as_document_server_sends_it_gives_its_fields(self):
        self.assertEqual(verify_callback(*callback(FIELDS), SECRET), FIELDS)

    def test_a_callback_signed_only_in_its_header_or_only_in_its_body_gives_its_fields(self):
        for header, body_token in ((True, False), (False, True)):
            with self.subTest(header=header, body_token=body_token):
                body, token = callback(FIELDS, header=header, body_token=body_token)
                self.assertEqual(verify_callback(body, token, SECRET), FIELDS)

    def test_a_body_of_only_a_token_gives_the_fields_it_signs(self):
        body, _header = callback(FIELDS, header=False)

        self.assertEqual(verify_callback({"token": body["token"]}, None, SECRET), FIELDS)

    def test_a_callback_without_a_token_is_refused(self):
        self.assertRefused(dict(FIELDS), None)

    def test_tokens_of_any_other_algorithm_are_refused(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        claims = {"payload": FIELDS, "exp": int(time.time()) + 300}
        for token in (
            jwt.encode(claims, None, algorithm="none"),
            jwt.encode(claims, SECRET, algorithm="HS384"),
            jwt.encode(claims, SECRET, algorithm="HS512"),
            jwt.encode(claims, pem, algorithm="RS256"),
        ):
            with self.subTest(algorithm=jwt.get_unverified_header(token)["alg"]):
                self.assertRefused(dict(FIELDS), f"Bearer {token}")

    def test_a_token_signed_with_another_secret_is_refused(self):
        self.assertRefused(*callback(FIELDS, secret="another-secret-of-the-same-length-0123456789"))

    def test_an_expired_token_is_refused_beyond_a_minute_of_clock_difference(self):
        self.assertRefused(*callback(FIELDS, lifetime=-120))
        self.assertEqual(verify_callback(*callback(FIELDS, lifetime=-30), SECRET), FIELDS)

    def test_a_token_without_an_expiry_is_refused(self):
        token = jwt.encode({"payload": FIELDS}, SECRET, algorithm="HS256")

        self.assertRefused(dict(FIELDS), f"Bearer {token}")

    def test_only_a_verified_expired_signature_is_classified_as_expired(self):
        for secret, expired in ((SECRET, True), ("other-test-secret-01234567890123456789", False)):
            body, header = callback(FIELDS, lifetime=-120, secret=secret)
            with self.assertRaises(EditingCallbackRefused) as refusal:
                verify_callback(body, header, SECRET)
            self.assertEqual(refusal.exception.expired, expired)

    def test_a_malformed_token_is_refused(self):
        for header, body in (
            ("Bearer abc", dict(FIELDS)),
            ("Basic abc", dict(FIELDS)),
            (None, {**FIELDS, "token": "abc"}),
            (None, {**FIELDS, "token": 123}),
        ):
            with self.subTest(header=header, body=body):
                self.assertRefused(body, header)

    def test_a_header_token_without_a_payload_is_refused(self):
        token = jwt.encode({**FIELDS, "exp": int(time.time()) + 300}, SECRET, algorithm="HS256")

        self.assertRefused(dict(FIELDS), f"Bearer {token}")

    def test_a_body_that_is_not_what_its_header_token_signs_is_refused(self):
        _body, header = callback(FIELDS, body_token=False)
        for body in (
            {**FIELDS, "url": "http://attacker.example/output.xlsx"},
            {**FIELDS, "users": ["1"]},
            {key: value for key, value in FIELDS.items() if key != "url"},
        ):
            with self.subTest(body=body):
                self.assertRefused(body, header)

    def test_a_body_that_is_not_what_its_body_token_signs_is_refused(self):
        body, _header = callback(FIELDS, header=False)

        self.assertRefused({**body, "status": 4}, None)

    def test_a_header_token_and_a_body_token_that_disagree_are_refused(self):
        body, _header = callback({**FIELDS, "status": 4}, header=False)
        _body, header = callback(FIELDS, body_token=False)

        self.assertRefused({"token": body["token"]}, header)

    def test_large_history_signed_before_native_trimming_is_still_refused(self):
        full = {
            **FIELDS,
            "changesurl": "http://onlyoffice/cache/changes.zip",
            "history": {"changes": [{"user": {"id": "7", "name": "editor" * 20}}] * 2000},
        }
        original, _header = callback(full)
        trimmed = {**FIELDS, "history": {}}
        _body, header = callback(trimmed)

        self.assertRefused({**trimmed, "token": original["token"]}, header)

    def test_consistently_trimmed_history_keeps_security_fields_bound(self):
        fields = {**FIELDS, "history": {}, "actions": [{"type": 0, "userid": "7"}]}
        body, header = callback(fields)

        self.assertEqual(verify_callback(body, header, SECRET), fields)
        for key, value in (
            ("key", "other-document"),
            ("status", 4),
            ("url", "http://attacker.example/output.xlsx"),
            ("users", ["999"]),
            ("actions", [{"type": 0, "userid": "999"}]),
            ("history", {"changes": [{"user": {"id": "999"}}]}),
        ):
            with self.subTest(field=key):
                self.assertRefused({**body, key: value}, header)

    def test_large_history_does_not_hide_invalid_or_malformed_tokens(self):
        fields = {**FIELDS, "history": {"changes": [{"user": {"id": "7", "name": "editor" * 20}}] * 2000}}
        body, header = callback(fields)
        invalid_body, invalid_header = callback(fields, secret="invalid-large-history-secret-01234567890123456789")
        self.assertRefused(body, invalid_header)
        self.assertRefused(invalid_body, header)
        for token in ("invalid.jwt", body["token"][:-1], None, {"token": body["token"]}, [body["token"]]):
            with self.subTest(token_type=type(token).__name__):
                self.assertRefused({**body, "token": token}, header)

    def test_a_token_of_another_operation_than_a_callback_is_refused(self):
        exp = int(time.time()) + 300
        for operation, accepted in (("callback", True), ("download", False)):
            token = jwt.encode({"payload": FIELDS, "operation": operation, "exp": exp}, SECRET, algorithm="HS256")
            with self.subTest(operation=operation):
                if accepted:
                    self.assertEqual(verify_callback(dict(FIELDS), f"Bearer {token}", SECRET), FIELDS)
                else:
                    self.assertRefused(dict(FIELDS), f"Bearer {token}")

    def test_without_the_secret_every_callback_is_refused(self):
        for secret in (None, ""):
            with self.subTest(secret=secret):
                self.assertRefused(*callback(FIELDS), secret=secret)

    def test_a_body_that_is_not_an_object_is_refused(self):
        _body, header = callback(FIELDS)

        self.assertRefused([FIELDS], header)

    def test_the_secret_comes_from_the_environment_and_is_at_least_32_bytes(self):
        without_secret = {name: value for name, value in os.environ.items() if name != JWT_SECRET_VARIABLE}
        with patch.dict(os.environ, without_secret, clear=True):
            self.assertIsNone(jwt_secret())
        for value, expected in (("", None), ("x" * 31, None), ("x" * 32, "x" * 32)):
            with self.subTest(length=len(value)), patch.dict(os.environ, {JWT_SECRET_VARIABLE: value}):
                self.assertEqual(jwt_secret(), expected)

    def test_a_signed_configuration_is_valid_for_its_lifetime(self):
        claims = jwt.decode(sign({"document": {"key": "k"}}, SECRET, 900), SECRET, algorithms=["HS256"])

        self.assertEqual(claims["document"], {"key": "k"})
        self.assertEqual(claims["exp"] - claims["iat"], 900)
