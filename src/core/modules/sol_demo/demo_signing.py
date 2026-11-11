import base64
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509.oid import NameOID

from odoo import fields

from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM, MODEL_SIGNING_CERTIFICATE
from odoo.addons.sol_laboratory.constants.settings import DIGITAL_SIGNING_PARAMETER
from odoo.addons.sol_laboratory.services.viettel_sign_client import ViettelSignError

LABORATORY = "Phòng Thử Nghiệm MediLab"
CERTIFICATE_AUTHORITY = "Viettel-CA (demo)"
DAYS_LEFT = 15
# Why the demo's Viettel Sign fails.
UNREACHABLE = "Viettel Sign could not be reached: ConnectionError"


def seed_signing(env):
    """The laboratory's certificate at Viettel Sign, 15 days from its expiry, the report sent by post issued with its
    PDF digitally signed with it, and a report pending digital signing because Viettel Sign failed when the lab head
    signed it. A key made for the demo stands in for Viettel Sign, which the demo cannot call."""
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
    records = [("demo_signing_certificate_laboratory", certificate)]
    lab_head = env.ref("sol_demo.demo_res_users_lab_head")
    by_post = env.ref("sol_demo.demo_test_report_by_post")
    # The reports wait for a prepared PDF when the demo templates could not be seeded.
    if by_post.candidate_ids:
        with _viettel_sign(env, lambda digest: key.sign(digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))):
            by_post.with_user(lab_head).action_sign()
        pending = env.ref("sol_demo.demo_test_report_pending")
        with _viettel_sign(env, None):
            pending.with_user(lab_head).action_sign()
        # The signing job gave up after its attempts, so it waits for someone to retry it rather than for the job, which
        # would issue the report unsigned while digital signing is off.
        item = env[MODEL_JOB_ITEM].search([("item_key", "=", pending._digital_signing_key())])
        item.write({"status": "failed", "attempts": item.job_id.max_attempts, "last_error": UNREACHABLE})
        records.append(("demo_digital_signature_by_post", by_post.digital_signature_id))

    env["ir.model.data"]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in records]
    )


@contextmanager
def _viettel_sign(env, sign):
    """Digital signing on, with Viettel Sign signing hashes through sign, or unreachable when sign is None."""

    class DemoViettelSign:
        def sign_hash(self, credential_id, digest, name):
            if sign is None:
                raise ViettelSignError(UNREACHABLE)
            return sign(digest)

    parameters = env["ir.config_parameter"].sudo()
    enabled = parameters.get_bool(DIGITAL_SIGNING_PARAMETER)
    parameters.set_bool(DIGITAL_SIGNING_PARAMETER, True)
    try:
        with patch(
            "odoo.addons.sol_laboratory.models.mixins.digital_signing_mixin.viettel_sign_client", DemoViettelSign
        ):
            yield
    finally:
        parameters.set_bool(DIGITAL_SIGNING_PARAMETER, enabled or None)


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
