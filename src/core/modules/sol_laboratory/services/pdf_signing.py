"""Signing a PDF with a signature made elsewhere, such as by Viettel Sign, and checking a signed PDF, with Odoo's
PAdES tools."""

import dataclasses
import hashlib
import io

from asn1crypto import cms, x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_der_x509_certificate, load_pem_x509_certificates

from odoo.tools.pdf import PdfFileReader, PdfReadError
from odoo.tools.pdf.signature import PdfSigner, build_cms_signature, build_signed_attributes, verify_signed_attributes


@dataclasses.dataclass(frozen=True)
class PdfCheck:
    """What the last signature of a PDF proves."""

    # True when the signature verifies with the certificate it carries and matches the bytes it covers.
    signature_valid: bool
    # True when the signature covers every byte of the file, so nothing was added after signing.
    whole_file: bool
    # DER of the certificate that made the signature.
    certificate: bytes


def certificate_chain(pem_chain):
    """The DER certificates of a PEM chain, in its order."""
    return [certificate.public_bytes(Encoding.DER) for certificate in load_pem_x509_certificates(pem_chain.encode())]


def pem_chain(chain):
    """The PEM text of DER certificates, in their order."""
    return "".join(load_der_x509_certificate(der).public_bytes(Encoding.PEM).decode() for der in chain)


def sign_pdf(pdf, chain, sign_digest):
    """The PDF with an invisible signature of the chain's first certificate; sign_digest returns the RSA signature of
    the SHA-256 digest it is given."""
    signer = PdfSigner(pdf)
    prepared = signer.write_signature_placeholder()
    if prepared is None:
        raise ValueError("The PDF cannot hold a signature.")
    certificates = [x509.Certificate.load(der) for der in chain]
    attributes = build_signed_attributes(prepared.digest, certificates[0])
    signature = sign_digest(hashlib.sha256(attributes.dump()).digest())
    content = build_cms_signature(attributes, signature, certificates[0], certificates[1:])
    return signer.fill_signature_placeholder(prepared, content.dump())


def check_pdf(data):
    """The check of the last signature of a PDF, or None when it has none or cannot be read."""
    try:
        fields = PdfFileReader(io.BytesIO(data), strict=False).get_fields() or {}
        values = [
            field["/V"].get_object() for field in fields.values() if field.get("/FT") == "/Sig" and field.get("/V")
        ]
        if not values:
            return None
        value = values[-1]
        byte_range = [int(number) for number in value["/ByteRange"]]
        signed_data = cms.ContentInfo.load(bytes(value["/Contents"]))["content"]
        signer_info = signed_data["signer_infos"][0]
        certificate = _signer_certificate(signed_data, signer_info)
        attributes = signer_info["signed_attrs"]
        message_digest = next(
            attribute["values"][0].native for attribute in attributes if attribute["type"].native == "message_digest"
        )
        covered = b"".join(data[start : start + length] for start, length in zip(byte_range[0::2], byte_range[1::2]))
        signature_valid = message_digest == hashlib.sha256(covered).digest() and verify_signed_attributes(
            attributes.untag(), signer_info["signature"].native, certificate
        )
    except (PdfReadError, KeyError, IndexError, StopIteration, TypeError, ValueError):
        return None
    whole_file = len(byte_range) == 4 and byte_range[0] == 0 and sum(byte_range[2:]) == len(data)
    return PdfCheck(signature_valid=signature_valid, whole_file=whole_file, certificate=certificate.dump())


def _signer_certificate(signed_data, signer_info):
    signer = signer_info["sid"].chosen
    for choice in signed_data["certificates"]:
        certificate = choice.chosen
        if certificate.issuer == signer["issuer"] and certificate.serial_number == signer["serial_number"].native:
            return certificate
    raise ValueError("The signature names no certificate the file carries.")
