import base64
import os
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import TransactionCase, tagged

from .signing_case import ACCOUNT
from odoo.addons.sol_laboratory.services.viettel_sign_client import (
    CLIENT_SECRET,
    DEFAULT_URL,
    RSA_OID,
    SHA256_OID,
    ViettelSignError,
    viettel_sign_client,
)

REQUESTS_POST = "odoo.addons.sol_laboratory.services.viettel_sign_client.requests.post"


def answer(body, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = body
    return response


@tagged("post_install", "-at_install")
class TestViettelSignClient(TransactionCase):
    """The client speaks Viettel Sign's remote signing API, with the account from the environment."""

    def setUp(self):
        super().setUp()
        self.startPatcher(patch.dict(os.environ, ACCOUNT))

    def test_signing_logs_in_then_signs_the_sha256_digest_with_rsa_and_waits_for_the_signature(self):
        signature = b"\x01" * 256
        with patch(REQUESTS_POST) as post:
            post.side_effect = [
                answer({"access_token": "session", "token_type": "Bearer", "expires_in": "3600"}),
                answer({"signatures": [base64.b64encode(signature).decode()]}),
            ]

            signed = viettel_sign_client().sign_hash("credential", b"\x02" * 32, "Phiếu kết quả PKQ.2026.0001")

        self.assertEqual(signed, signature)
        login, sign = post.call_args_list
        self.assertEqual(login.args[0], f"{DEFAULT_URL}/vtss/service/ras/v1/login")
        self.assertEqual(login.kwargs["json"]["user_id"], ACCOUNT["VIETTEL_SIGN_USER_ID"])
        self.assertEqual(sign.args[0], f"{DEFAULT_URL}/vtss/service/signHash")
        self.assertEqual(sign.kwargs["headers"], {"Authorization": "Bearer session"})
        body = sign.kwargs["json"]
        self.assertEqual(body["credentialID"], "credential")
        self.assertEqual(body["hash"], [base64.b64encode(b"\x02" * 32).decode()])
        self.assertEqual((body["hashAlgo"], body["signAlgo"], body["async"]), (SHA256_OID, RSA_OID, 0))
        self.assertEqual(body["documents"][0]["document_id"], "Phieu ket qua PKQ20260001")

    def test_an_error_answer_raises(self):
        for response in (
            answer({"error": "58002", "error_description": "Service is not available"}, 400),
            answer({"error": "59033"}),
        ):
            with self.subTest(response=response), patch(REQUESTS_POST, return_value=response):
                with self.assertRaises(ViettelSignError):
                    viettel_sign_client().certificates()

    def test_an_unreachable_service_raises(self):
        with patch(REQUESTS_POST, side_effect=requests.ConnectionError("refused")), self.assertRaises(ViettelSignError):
            viettel_sign_client().certificates()

    def test_a_missing_variable_refuses_before_any_call(self):
        with patch.dict(os.environ, {CLIENT_SECRET: ""}), patch(REQUESTS_POST) as post:
            with self.assertRaises(ViettelSignError):
                viettel_sign_client()

        post.assert_not_called()
