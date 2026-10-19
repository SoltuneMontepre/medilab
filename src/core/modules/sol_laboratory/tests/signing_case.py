import base64
import io
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509.oid import NameOID

from odoo.tools.pdf import PdfFileWriter

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_DIGITAL_SIGNATURE, MODEL_SIGNING_CERTIFICATE
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.constants.signing import CERTIFICATE_REVOKED
from odoo.addons.sol_laboratory.services.viettel_sign_client import (
    CLIENT_ID,
    CLIENT_SECRET,
    PROFILE_ID,
    USER_ID,
    ViettelSignClient,
    ViettelSignError,
)

CREDENTIAL = "0312345678-998_2475106_20260101"
ACCOUNT = {CLIENT_ID: "medilab", CLIENT_SECRET: "client-secret", PROFILE_ID: "profile", USER_ID: "MST_0312345678-998"}
SIGN_HASH = "/vtss/service/signHash"


def self_signed(name, days):
    """A private key and the DER of a certificate of it that stays valid for the days given."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    return key, certificate.public_bytes(serialization.Encoding.DER)


def blank_pdf():
    writer = PdfFileWriter()
    writer.add_blank_page(width=595, height=842)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


class FakeViettelSign:
    """Viettel Sign as its API answers: it logs in, reports the laboratory's certificate and signs hashes with its key.
    While down, every call fails as an unreachable service does."""

    def __init__(self, key, der):
        self.key = key
        self.der = der
        # The key that signs hashes; another key than the certificate's makes signatures it does not verify.
        self.signing_key = key
        self.down = False
        self.certificate_status = "valid"
        self.key_status = "ENABLED"
        self.calls = []

    def post(self, client, path, payload, token=None):
        self.calls.append((path, payload, token))
        if self.down:
            raise ViettelSignError("Viettel Sign could not be reached: ConnectionError")
        if path.endswith("/login"):
            return {"access_token": "session", "token_type": "Bearer", "expires_in": "3600"}
        if path.endswith("/certificates/info"):
            return [
                {
                    "credential_id": CREDENTIAL,
                    "key": {"status": self.key_status, "algo": ["1.2.840.113549.1.1.1"], "len": 2048},
                    "cert": {"status": self.certificate_status, "certificates": [base64.b64encode(self.der).decode()]},
                    "authMode": "implicit",
                }
            ]
        digest = base64.b64decode(payload["hash"][0])
        signature = self.signing_key.sign(digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
        return {"signatures": [base64.b64encode(signature).decode()]}

    def signings(self):
        return [call for call in self.calls if call[0] == SIGN_HASH]


class SigningCase(ReportCase):
    """Digital signing is on, with a Viettel Sign account whose laboratory certificate is valid for a year. Reports
    render as a blank PDF, since tests have no PDF engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key, cls.der = self_signed("Phong Thu Nghiem An Phu", 365)
        cls.pdf = blank_pdf()

    def setUp(self):
        super().setUp()
        self.viettel = FakeViettelSign(self.key, self.der)
        viettel = self.viettel
        self.patch(
            ViettelSignClient,
            "_post",
            lambda client, path, payload, token=None: viettel.post(client, path, payload, token),
        )
        self.startPatcher(patch.dict(os.environ, ACCOUNT))
        pdf = self.pdf

        def pre_render(printing, report_ref, res_ids=None, data=None):
            res_id = res_ids if isinstance(res_ids, int) else (res_ids or [False])[0]
            return {res_id: {"stream": io.BytesIO(pdf), "attachment": None}}, "pdf"

        self.patch(type(self.env["ir.actions.report"]), "_pre_render_qweb_pdf", pre_render)
        self.env["ir.config_parameter"].set_bool(DIGITAL_SIGNING_PARAMETER, True)
        certificates = self.env[MODEL_SIGNING_CERTIFICATE]
        certificates._refresh()
        # Certificates the database already holds, such as the demo data's, do not sign in these tests.
        certificates.search([("credential_id", "!=", CREDENTIAL)]).write({"status": CERTIFICATE_REVOKED})

    def digital_signature(self, report):
        return self.env[MODEL_DIGITAL_SIGNATURE].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id)]
        )

    def issue(self):
        """The report of the lead request, signed by the lab head."""
        self.complete()
        report = self.report()
        self.sign(report)
        return report
