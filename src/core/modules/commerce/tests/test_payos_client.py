import logging
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from .payos_case import CREDENTIALS, enable_payos, fake_payos, signed_answer
from odoo.addons.commerce.constants.payos import ENV_API_KEY, ENV_CHECKSUM_KEY, ENV_CLIENT_ID, TIMEOUT_SECONDS
from odoo.addons.commerce.services.payos_client import PayosClient, PayosError, PayosUnavailable, sign, verify

# The signature of PayOS's own documentation example: sorted keys, key=value pairs joined by &, HMAC-SHA256 hex.
REFERENCE_DATA = {
    "orderCode": 123,
    "amount": 3000,
    "description": "VQRIO123",
    "accountNumber": "12345678",
    "reference": "TF230204212323",
    "transactionDateTime": "2023-02-04 18:25:00",
    "currency": "VND",
    "paymentLinkId": "124c33293c43417ab7879e14c8d9eb18",
    "code": "00",
    "desc": "Thành công",
    "counterAccountBankId": "",
    "counterAccountBankName": "",
    "counterAccountName": "",
    "counterAccountNumber": "",
    "virtualAccountName": "",
    "virtualAccountNumber": "",
}
REFERENCE_KEY = "test-checksum-key"
REFERENCE_MESSAGE = (
    "accountNumber=12345678&amount=3000&code=00&counterAccountBankId=&counterAccountBankName=&counterAccountName=&"
    "counterAccountNumber=&currency=VND&desc=Thành công&description=VQRIO123&orderCode=123&"
    "paymentLinkId=124c33293c43417ab7879e14c8d9eb18&reference=TF230204212323&"
    "transactionDateTime=2023-02-04 18:25:00&virtualAccountName=&virtualAccountNumber="
)


@tagged("post_install", "-at_install")
class TestPayosClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        enable_payos(cls)

    def test_the_signature_is_the_hmac_of_the_sorted_query_string(self):
        import hashlib
        import hmac

        expected = hmac.new(REFERENCE_KEY.encode(), REFERENCE_MESSAGE.encode(), hashlib.sha256).hexdigest()

        self.assertEqual(sign(REFERENCE_DATA, REFERENCE_KEY), expected)
        self.assertTrue(verify(REFERENCE_DATA, expected, REFERENCE_KEY))
        self.assertFalse(verify(REFERENCE_DATA, expected, "another-key"))
        self.assertFalse(verify(REFERENCE_DATA, None, REFERENCE_KEY))
        self.assertFalse(verify(REFERENCE_DATA, sign(REFERENCE_DATA, ""), ""))

    def test_none_booleans_and_lists_are_signed_as_payos_does(self):
        data = {"a": None, "b": True, "c": False, "d": [{"y": 1, "x": "2"}], "e": "null"}

        self.assertEqual(
            sign(data, "k"), sign({"a": "", "b": "true", "c": "false", "d": '[{"x":"2","y":1}]', "e": ""}, "k")
        )

    def test_is_configured_needs_the_three_variables(self):
        self.assertTrue(PayosClient().is_configured())
        for missing in (ENV_CLIENT_ID, ENV_API_KEY, ENV_CHECKSUM_KEY):
            with self.subTest(missing=missing):
                self.assertFalse(PayosClient({**CREDENTIALS, missing: ""}).is_configured())

    def test_the_create_request_is_signed_and_sent_with_the_headers_and_timeout(self):
        captured = {}

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return signed_answer({"orderCode": 7, "status": "PENDING", "checkoutUrl": "https://pay.payos.vn/web/x"})

        def request(method, url, json=None, headers=None, timeout=None):
            captured.update(method=method, url=url, json=json, headers=headers, timeout=timeout)
            return Response()

        with patch("odoo.addons.commerce.services.payos_client.requests.request", request):
            data = PayosClient().create_payment_link(7, 2_700_000, "000126HD", "https://r", "https://c", 1_700_000_000)

        self.assertEqual(data["checkoutUrl"], "https://pay.payos.vn/web/x")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "https://api-merchant.payos.vn/v2/payment-requests")
        self.assertEqual(captured["timeout"], TIMEOUT_SECONDS)
        self.assertEqual(captured["headers"], {"x-client-id": "test-client-id", "x-api-key": "test-api-key"})
        body = captured["json"]
        self.assertEqual(body["expiredAt"], 1_700_000_000)
        expected = sign(
            {
                "amount": 2_700_000,
                "cancelUrl": "https://c",
                "description": "000126HD",
                "orderCode": 7,
                "returnUrl": "https://r",
            },
            CREDENTIALS["PAYOS_CHECKSUM_KEY"],
        )
        self.assertEqual(body["signature"], expected)

    def test_a_wrongly_signed_answer_is_refused(self):
        answer = signed_answer({"orderCode": 7, "status": "PAID"})
        answer["data"]["status"] = "PENDING"
        fake_payos(self, {("GET", "/v2/payment-requests/"): answer})

        with self.assertRaises(PayosError):
            PayosClient().get_payment_link(7)

    def test_an_error_code_raises_with_its_description(self):
        fake_payos(self, {("GET", "/v2/payment-requests/"): {"code": "101", "desc": "Mã thanh toán không tồn tại"}})

        with self.assertRaises(PayosError) as raised:
            PayosClient().get_payment_link(7)

        self.assertEqual(raised.exception.code, "101")
        self.assertIn("không tồn tại", str(raised.exception))

    def test_network_and_server_errors_are_unavailable(self):
        import requests

        class ServerError:
            status_code = 503

            @staticmethod
            def json():
                return {}

        def down(*args, **kwargs):
            raise requests.ConnectionError("refused")

        with (
            patch("odoo.addons.commerce.services.payos_client.requests.request", down),
            self.assertRaises(PayosUnavailable),
        ):
            PayosClient().get_payment_link(7)
        with (
            patch("odoo.addons.commerce.services.payos_client.requests.request", lambda *a, **k: ServerError()),
            self.assertRaises(PayosUnavailable),
        ):
            PayosClient().get_payment_link(7)

    def test_the_log_names_the_call_but_never_a_credential(self):
        fake_payos(self, {("GET", "/v2/payment-requests/"): signed_answer({"orderCode": 7, "status": "PENDING"})})

        with self.assertLogs("odoo.addons.commerce.services.payos_client", level=logging.INFO) as logs:
            PayosClient().get_payment_link(7)

        text = "\n".join(logs.output)
        self.assertIn("GET /v2/payment-requests/7 order 7", text)
        for secret in CREDENTIALS.values():
            self.assertNotIn(secret, text)
