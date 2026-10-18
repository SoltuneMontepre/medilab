import base64
import io
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509.oid import NameOID

from odoo import fields
from odoo.tools.pdf import PdfFileWriter

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_REPORT, MODEL_SIGNING_CERTIFICATE
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.constants.signing import UNSIGNED_PRINT_CONTEXT
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT
from odoo.addons.sol_laboratory.services.pdf_signing import sign_pdf

LABORATORY = "Phòng Thử Nghiệm MediLab"
CERTIFICATE_AUTHORITY = "Viettel-CA (demo)"
DAYS_LEFT = 15


def seed_signing(env):
    """The laboratory's certificate at Viettel Sign, 15 days from its expiry, and the report sent by post digitally
    signed with it. A key made for the demo stands in for Viettel Sign, which the demo cannot call."""
    if env.ref("sol_demo.demo_signing_certificate_laboratory", raise_if_not_found=False):
        return
    key, chain = _chain()
    certificates = env[MODEL_SIGNING_CERTIFICATE]
    # Stored the way Viettel Sign reports a certificate.
    reported = {
        "credential_id": "0312345678-998_2475106_demo",
        "key": {"status": "ENABLED"},
        "cert": {"status": "valid", "certificates": [base64.b64encode(der).decode() for der in chain]},
    }
    certificate = certificates.create(certificates._reported_values(reported, fields.Datetime.now()))
    report = env.ref("sol_demo.demo_test_report_by_post")
    unsigned = report.attachment_id
    signed = sign_pdf(
        _report_pdf(env, report),
        chain,
        lambda digest: key.sign(digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256())),
    )
    signature = report._digital_signing_store(signed, certificate)
    unsigned.unlink()

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_signing_certificate_laboratory", "record": certificate, "noupdate": True},
            {"xml_id": "sol_demo.demo_digital_signature_by_post", "record": signature, "noupdate": True},
        ]
    )


def _chain():
    """The laboratory's key, and the DER of its certificate followed by that of the demo authority that issued it."""
    now = datetime.now(UTC)
    authority_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    authority = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CERTIFICATE_AUTHORITY)])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    laboratory = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "VN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, LABORATORY),
            x509.NameAttribute(NameOID.COMMON_NAME, LABORATORY),
        ]
    )
    certificates = (
        _certificate(laboratory, authority, key, authority_key, now + timedelta(days=DAYS_LEFT)),
        _certificate(authority, authority, authority_key, authority_key, now + timedelta(days=3650)),
    )
    return key, [certificate.public_bytes(serialization.Encoding.DER) for certificate in certificates]


def _certificate(subject, issuer, key, issuer_key, valid_to):
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_to - timedelta(days=365))
        .not_valid_after(valid_to)
        .sign(issuer_key, hashes.SHA256())
    )


def _report_pdf(env, report):
    """The report as it prints once digital signing is on, with the address of the verification page."""
    parameters = env["ir.config_parameter"].sudo()
    enabled = parameters.get_bool(DIGITAL_SIGNING_PARAMETER)
    parameters.set_bool(DIGITAL_SIGNING_PARAMETER, True)
    content, report_type = (
        env[MODEL_IR_ACTIONS_REPORT]
        .with_context(**{UNSIGNED_PRINT_CONTEXT: True})
        ._render_qweb_pdf(TEST_REPORT_REPORT, report.ids)
    )
    parameters.set_bool(DIGITAL_SIGNING_PARAMETER, enabled or None)
    if report_type == "pdf":
        return content
    # Tests render reports as HTML, so a blank page stands in for the PDF there.
    writer = PdfFileWriter()
    writer.add_blank_page(width=595, height=842)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()
