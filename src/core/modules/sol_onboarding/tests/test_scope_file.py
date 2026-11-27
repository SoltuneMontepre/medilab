from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import file_open
from odoo.tools.binary import BinaryBytes

from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import CRAWL_JOB
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

BOA = "https://www.boa.gov.vn"
ORGANISATION = f"{BOA}/vi/phong-hoa-nghiem-xang-dau"
DECISION = f"{BOA}/sites/default/files/img_import/001l0624-q12WLI8TI0WtpCLg.pdf"
ANNEX = f"{BOA}/sites/default/files/img_import/001-Sfy3iWcRtcTFXUvw.pdf"


def recorded(name):
    with file_open(f"sol_onboarding/tests/pages/boa/{name}", "rb") as page:
        return page.read()


@tagged("post_install", "-at_install")
class TestScopeFile(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.boa = cls.env[MODEL_ONBOARDING_SOURCE].sudo().search([("adapter", "=", "boa")], order="id", limit=1)

    def run_of(self, name="annex.pdf", **values):
        file = BinaryBytes(recorded(name), filename=name)
        run = self.env[MODEL_ONBOARDING_RUN].with_user(self.admin)
        return run.create({"scope_file": file, "scope_filename": name, **values})

    def collect(self, run):
        run.action_start()
        self.run_until_settled(CRAWL_JOB)
        return run.sudo()

    def listed(self, code):
        return (
            self.env[MODEL_ONBOARDING_ORGANISATION]
            .sudo()
            .create(
                {
                    "source_id": self.boa.id,
                    "external_key": "phong-hoa-nghiem-xang-dau",
                    "name": "Phòng Hóa nghiệm Xăng Dầu",
                    "accreditation_code": code,
                    "url": ORGANISATION,
                    "seen_at": fields.Datetime.now(),
                }
            )
        )

    def test_a_scope_file_stages_its_certificate_fields_and_methods(self):
        run = self.collect(self.run_of())

        certificate = run.staged_record_ids.filtered(lambda record: record.kind == "certificate")
        methods = run.staged_record_ids.filtered(lambda record: record.kind == "testing_method")
        self.assertEqual(run.state, "done")
        self.assertEqual(
            certificate.source_values,
            {"code": "VILAS 001", "issuing_body": "BoA", "valid_from": "", "valid_until": "2029-07-05"},
        )
        self.assertEqual(len(methods), 12)
        self.assertEqual(methods.parent_id, certificate)
        self.assertEqual(
            certificate.page_url, f"/web/content/medilab.onboarding.run/{run.id}/scope_file/annex.pdf?download=true"
        )
        self.assertFalse(run.organisation_id)
        self.assertIn("read the uploaded file annex.pdf", run.log or "")
        self.assertIn("No listed organisation has the accreditation number", run.log or "")

    def test_the_same_scope_file_stages_nothing_again(self):
        self.collect(self.run_of())

        again = self.collect(self.run_of())

        self.assertEqual((again.state, again.staged_count), ("done", 0))

    def test_a_scope_file_adds_nothing_to_what_the_source_publishes(self):
        self.boa.enabled = True
        self.serve(
            {
                ORGANISATION: (200, "text/html; charset=UTF-8", recorded("organisation.html"), {}),
                DECISION: (200, "application/pdf", recorded("decision.pdf"), {}),
                ANNEX: (200, "application/pdf", recorded("annex.pdf"), {}),
            }
        )
        organisation = self.listed("VILAS 001")

        run = self.collect(self.run_of())

        self.assertEqual(run.organisation_id, organisation)
        self.assertEqual(len(run.snapshot_ids), 4)
        kinds = run.staged_record_ids.mapped("kind")
        self.assertEqual((kinds.count("certificate"), kinds.count("testing_method")), (1, 12))
        certificate = run.staged_record_ids.filtered(lambda record: record.kind == "certificate")
        self.assertEqual(certificate.page_url, ORGANISATION)
        self.assertEqual(certificate.child_ids, run.staged_record_ids.filtered(lambda r: r.kind == "testing_method"))

    def test_a_scope_file_of_another_organisation_is_refused(self):
        self.listed("VILAS 002")
        organisation = self.env[MODEL_ONBOARDING_ORGANISATION].search([("accreditation_code", "=", "VILAS 002")])
        run = self.run_of(organisation_id=organisation.id)

        with self.assertRaisesRegex(ValidationError, "VILAS 001.*VILAS 002"):
            run.action_start()
        self.assertEqual(run.state, "draft")

    def test_a_file_without_a_list_of_accredited_tests_is_refused(self):
        for name in ("decision.pdf", "organisation.html"):
            with self.subTest(name=name), self.assertRaisesRegex(ValidationError, "list of accredited tests"):
                self.run_of(name).action_start()

    def test_a_scope_file_is_read_while_its_source_is_turned_off(self):
        self.assertFalse(self.boa.enabled)

        run = self.collect(self.run_of())

        self.assertEqual((run.state, run.skipped_count), ("done", 0))
        self.assertTrue(run.staged_record_ids)
