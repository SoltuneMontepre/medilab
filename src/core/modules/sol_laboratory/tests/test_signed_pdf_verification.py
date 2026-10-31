import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils

from odoo import models
from odoo.tests import HttpCase, tagged

from .signing_case import SigningCase, self_signed
from odoo.addons.sol_laboratory.constants.models import MODEL_DIGITAL_SIGNATURE
from odoo.addons.sol_laboratory.services.model_lookup import record_as
from odoo.addons.sol_laboratory.services.pdf_signing import sign_pdf
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

CSRF_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


@tagged("post_install", "-at_install")
class TestSignedPdfVerification(HttpCase, SigningCase):
    """The issued lead report's signed PDF, checked as a customer would on the public page."""

    def verify(self, data):
        return self.env[MODEL_DIGITAL_SIGNATURE]._verify_file(data)

    def signed_pdf(self):
        return bytes(self.issue().attachment_id.raw)

    def test_the_signed_pdf_is_valid_and_shows_who_approved_it(self):
        report = self.issue()

        result = self.verify(bytes(report.attachment_id.raw))

        self.assertTrue(result["valid"])
        self.assertEqual(result["signature"], self.digital_signature(report))
        approvals = record_as(
            assert_instance(result["signature"], models.BaseModel), self.env[MODEL_DIGITAL_SIGNATURE]
        )._approvals()
        self.assertEqual(approvals.signer_id, self.lab_head)
        self.assertEqual(approvals.level_name, "Lab head")

    def test_a_signed_pdf_fails_verification_when_any_of_its_content_changes(self):
        pdf = self.signed_pdf()
        # A byte of the page the signature covers, far from the signature itself.
        changed = pdf.replace(b"/MediaBox", b"/MediaBoy", 1)

        result = self.verify(changed)

        self.assertNotEqual(changed, pdf)
        self.assertFalse(result["valid"])
        self.assertFalse(result.get("signature_valid"))
        self.assertFalse(result.get("unchanged"))

    def test_content_added_after_signing_fails_verification(self):
        result = self.verify(self.signed_pdf() + b"\n% added after signing\n")

        self.assertFalse(result["valid"])
        self.assertFalse(result["unchanged"])

    def test_a_pdf_without_a_digital_signature_is_not_valid(self):
        result = self.verify(self.pdf)

        self.assertEqual((result["signed"], result["valid"]), (False, False))

    def test_a_pdf_signed_with_another_certificate_is_not_the_laboratorys(self):
        self.signed_pdf()
        key, der = self_signed("Someone Else", 365)

        forged = sign_pdf(
            self.pdf, [der], lambda digest: key.sign(digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
        )
        result = self.verify(forged)

        self.assertTrue(result["signature_valid"])
        self.assertFalse(result["laboratory_certificate"])
        self.assertFalse(result["valid"])

    def test_anyone_verifies_a_signed_pdf_on_the_public_page_without_signing_in(self):
        report = self.issue()
        page = self.url_open("/verify")
        self.assertEqual(page.status_code, 200)
        token = CSRF_TOKEN.search(page.text)
        if token is None:
            self.fail("The verification form has no CSRF token.")

        response = self.url_open(
            "/verify",
            data={"csrf_token": token.group(1)},
            files={"document": ("report.pdf", bytes(report.attachment_id.raw), "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Valid:", response.text)
        self.assertEqual(response.text.count(">Passed<"), 3)
        self.assertNotIn(">Failed<", response.text)
        self.assertIn(report.code, response.text)
        self.assertIn(self.lab_head.name, response.text)
