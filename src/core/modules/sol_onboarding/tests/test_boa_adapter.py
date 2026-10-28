import unicodedata

from odoo import fields
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import CRAWL_JOB
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, Parsed
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for
from odoo.addons.sol_onboarding.services.parsing import pdf_text
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

BOA = "https://www.boa.gov.vn"
LIST = f"{BOA}/vi/timkiem/tochuc"
ORGANISATION = f"{BOA}/vi/phong-hoa-nghiem-xang-dau"
SECOND_ORGANISATION = f"{BOA}/vi/phong-thu-nghiem-9972"
FIRST_PDF = f"{BOA}/sites/default/files/img_import/001l0624-q12WLI8TI0WtpCLg.pdf"
SECOND_PDF = f"{BOA}/sites/default/files/img_import/001-Sfy3iWcRtcTFXUvw.pdf"
SCOPE = [
    "GOST 8226-22",
    "ASTM D2699-23",
    "ASTM D323-20a",
    "ASTM D5191-20",
    "GOST 4039-88",
    "ASTM D525-12a (2019)",
    "TCVN 3166:2019",
    "ASTM D5580-21",
    "TCVN 7332:2013",
    "ASTM D4815-22",
    "ASTM D6371-17a",
    "ASTM D6079-22",
]
# BoA's pages declare UTF-8 in a meta tag; html_tree reads bytes without one as Latin-1.
CHARSET = '<meta charset="utf-8">'


def recorded(name):
    with file_open(f"sol_onboarding/tests/pages/boa/{name}", "rb") as page:
        return page.read()


@tagged("post_install", "-at_install")
class TestBoaAdapter(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.boa = (
            cls.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .create({"name": "BoA", "adapter": "boa", "host": "www.boa.gov.vn", "start_url": LIST, "enabled": True})
        )

    def parse_body(self, url, content_type, body):
        return adapter_for(self.boa).parse(Fetched(url, content_type, body, fields.Datetime.now()), None)

    def parse(self, url, content_type, name):
        return self.parse_body(url, content_type, recorded(name))

    def collect(self, organisation):
        run = self.env[MODEL_ONBOARDING_RUN].with_user(self.admin).create({"organisation_id": organisation.id})
        run.action_start()
        self.run_until_settled(CRAWL_JOB)
        return run.sudo()

    def served_organisation(self):
        """The recorded organisation, served with its decision and annex."""
        self.serve(
            {
                ORGANISATION: (200, "text/html; charset=UTF-8", recorded("organisation.html"), {}),
                FIRST_PDF: (200, "application/pdf", recorded("decision.pdf"), {}),
                SECOND_PDF: (200, "application/pdf", recorded("annex.pdf"), {}),
            }
        )
        return (
            self.env[MODEL_ONBOARDING_ORGANISATION]
            .sudo()
            .create(
                {
                    "source_id": self.boa.id,
                    "external_key": "phong-hoa-nghiem-xang-dau",
                    "name": "Phòng Hóa nghiệm Xăng Dầu",
                    "url": ORGANISATION,
                    "seen_at": fields.Datetime.now(),
                }
            )
        )

    def test_lists_the_organisations_of_a_list_page(self):
        parsed = self.parse(LIST, "html", "organisations.html")
        self.assertEqual(
            [(o.key, o.name, o.accreditation_code, o.url, o.tax_id) for o in parsed.organisations],
            [
                (
                    "cong-ty-tnhh-biolytrics-viet-nam-0",
                    "Công ty TNHH Biolytrics Việt Nam",
                    "GLP OECD 001",
                    f"{BOA}/vi/cong-ty-tnhh-biolytrics-viet-nam-0",
                    None,
                ),
                (
                    "trung-tam-quan-trac-moi-truong-mien-trung-va-tay-nguyen",
                    "Trung tâm Quan trắc môi trường miền Trung và Tây Nguyên (Cục Môi trường)",
                    "VIPAS 001",
                    f"{BOA}/vi/trung-tam-quan-trac-moi-truong-mien-trung-va-tay-nguyen",
                    None,
                ),
                ("cong-ty-tnhh-iits-0", "CÔNG TY TNHH IITS", "VIAS 001", f"{BOA}/vi/cong-ty-tnhh-iits-0", None),
                (
                    "phong-hoa-nghiem-xang-dau",
                    "Phòng Hóa nghiệm Xăng Dầu (Viện Kỹ thuật Xăng dầu Quân Đội - Cục Xăng dầu - Tổng cục Hậu Cần)",
                    "VILAS 001",
                    ORGANISATION,
                    None,
                ),
            ],
        )
        self.assertEqual(parsed.links, (f"{LIST}?page=1",))
        self.assertEqual(parsed.records, ())

    def test_the_last_list_page_links_nowhere(self):
        parsed = self.parse(f"{LIST}?page=191", "html", "organisations-last.html")
        self.assertEqual([o.accreditation_code for o in parsed.organisations], ["VILAS 139"])
        self.assertEqual(parsed.links, ())

    def test_an_organisation_page_stages_its_certificate_and_links_its_scope(self):
        parsed = self.parse(ORGANISATION, "html", "organisation.html")
        [certificate] = parsed.records
        self.assertEqual(
            (certificate.kind, certificate.key, certificate.values, certificate.lang, certificate.parent),
            (
                "certificate",
                "VILAS 001",
                {"code": "VILAS 001", "issuing_body": "BoA", "valid_from": "", "valid_until": "2029-07-05"},
                "en_US",
                None,
            ),
        )
        self.assertEqual(parsed.links, (FIRST_PDF, SECOND_PDF))

    def test_an_organisation_page_stages_only_what_it_shows(self):
        body = f'{CHARSET}<div class="label-maso">Mã số công nhận</div><div class="detail-maso">VILAS 9971</div>'
        parsed = self.parse_body(ORGANISATION, "html", body.encode())
        [certificate] = parsed.records
        self.assertEqual(
            certificate.values, {"code": "VILAS 9971", "issuing_body": "BoA", "valid_from": "", "valid_until": ""}
        )
        self.assertEqual(parsed.links, ())
        self.assertEqual(self.parse_body(ORGANISATION, "html", f"{CHARSET}<p>Không tìm thấy</p>".encode()), Parsed())
        uncoded = f'{CHARSET}<fieldset id="tochuc-congnhan"><a href="{SECOND_PDF}">Xem</a></fieldset>'
        self.assertEqual(self.parse_body(ORGANISATION, "html", uncoded.encode()), Parsed())

    def test_the_annex_stages_its_field_and_methods_under_the_certificate(self):
        field, *methods = self.parse(SECOND_PDF, "pdf", "annex.pdf").records
        self.assertEqual(
            (field.kind, field.key, field.values, field.lang, field.parent),
            ("testing_field", "Hóa", {"code": "", "name": "Chemical"}, "en_US", None),
        )
        self.assertEqual([method.key for method in methods], [f"VILAS 001: {code}" for code in SCOPE])
        self.assertEqual([method.values["code"] for method in methods], SCOPE)
        self.assertEqual(
            {(m.kind, m.parent, m.values["field_key"], m.lang) for m in methods},
            {("testing_method", ("certificate", "VILAS 001"), "Hóa", "en_US")},
        )
        titles = {method.values["code"]: method.values["name"] for method in methods}
        self.assertEqual(titles["GOST 8226-22"], "Determination of Octan number Engine method")
        self.assertEqual(titles["ASTM D323-20a"], "Determination of saturated vapor pressure")
        self.assertEqual(titles["ASTM D6371-17a"], "Determination of Cold Filter Plugging Point temperature")

    def test_the_decision_stages_nothing(self):
        self.assertEqual(self.parse(FIRST_PDF, "pdf", "decision.pdf"), Parsed())

    def test_method_codes_are_read_however_the_pdf_spaces_them(self):
        text = (
            "LIST OF ACCREDITED TESTS\nSố hiệu/ Code: VILAS 9971\nLĩnh vực thử nghiệm: Hóa\n"
            "Field of testing: Chemical\n1. Determination of colour 0 8,0 ASTM D 1500 -24 \n(2017)\n"
            "2. Determination of gum GOST 11802 -88(e2003) ASTM D 1500 -24 (2017)\n3. Xác định\n TCVN 7272:10\n"
        )
        adapter = adapter_for(self.boa)
        methods = adapter._annex(text)[1:]
        self.assertEqual(
            [(m.key, m.values["name"]) for m in methods],
            [
                ("VILAS 9971: ASTM D1500-24 (2017)", "Determination of colour"),
                ("VILAS 9971: GOST 11802-88 (e2003)", "Determination of gum"),
                ("VILAS 9971: TCVN 7272:10", "TCVN 7272:10"),
            ],
        )
        self.assertEqual(adapter._annex(unicodedata.normalize("NFD", text)), adapter._annex(text))

    def test_method_codes_keep_every_part_of_the_standard(self):
        text = (
            "LIST OF ACCREDITED TESTS\nSố hiệu/ Code: VILAS 9971\nLĩnh vực thử nghiệm: Hóa\n"
            "Field of testing: Chemical\n1. ASTM D525-12a (2019)\n2. ASTM D6371-17a\n3. ASTM D 1500 -24\n(2017)\n"
            "4. SMEWW 3113B:2017\n5. EPA 8270D\n6. Determination of nitrate SMEWW 4500-NO3-.E:2017\n"
            "7. Determination of phosphorus SMEWW 4500-P.E:2017\n8. SMEWW 4500-H+.B:2017\n9. BS EN 12393-1:2013\n"
            "10. ISO 6579-1:2017\n11. TCVN 7924-2:2008\n12. AOAC Official Method 2015.01\n13. US EPA Method 200.8\n"
            "14. ISO/IEC 17025:2017\n"
        )
        methods = adapter_for(self.boa)._annex(text)[1:]
        self.assertEqual(
            [m.values["code"] for m in methods],
            [
                "ASTM D525-12a (2019)",
                "ASTM D6371-17a",
                "ASTM D1500-24 (2017)",
                "SMEWW 3113B:2017",
                "EPA 8270D",
                "SMEWW 4500-NO3-.E:2017",
                "SMEWW 4500-P.E:2017",
                "SMEWW 4500-H+.B:2017",
                "BS EN 12393-1:2013",
                "ISO 6579-1:2017",
                "TCVN 7924-2:2008",
                "AOAC 2015.01",
                "EPA 200.8",
            ],
        )
        titles = {m.values["code"]: m.values["name"] for m in methods}
        self.assertEqual(
            (titles["SMEWW 4500-NO3-.E:2017"], titles["SMEWW 4500-P.E:2017"]),
            ("Determination of nitrate", "Determination of phosphorus"),
        )

    def test_collecting_an_organisation_stages_its_scope_once(self):
        organisation = self.served_organisation()
        run = self.collect(organisation)

        self.assertEqual((run.state, len(run.snapshot_ids)), ("done", 3))
        staged = run.staged_record_ids
        certificate = staged.filtered(lambda record: record.kind == "certificate")
        self.assertEqual(certificate.external_key, "VILAS 001")
        self.assertEqual(
            sorted(certificate.child_ids.mapped("external_key")), sorted(f"VILAS 001: {code}" for code in SCOPE)
        )
        self.assertEqual(staged.filtered(lambda record: record.kind == "testing_field").mapped("external_key"), ["Hóa"])
        self.assertFalse(self.collect(organisation).staged_record_ids)

    def test_two_organisations_sharing_a_method_each_list_it(self):
        first = self.collect(self.served_organisation()).staged_record_ids.filtered(
            lambda record: record.kind == "certificate"
        )
        # The recorded annex cannot be edited, so the second organisation's annex is its text under another code.
        page = recorded("organisation.html").replace(b"VILAS 001", b"VILAS 9972")
        fetched = Fetched(SECOND_ORGANISATION, "html", page, fields.Datetime.now())
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(
            self.env[MODEL_ONBOARDING_RUN].create({}), self.boa, fetched
        )
        adapter = adapter_for(self.boa)
        annex = adapter._annex(pdf_text(recorded("annex.pdf")).replace("VILAS 001", "VILAS 9972"))
        second = (
            self.env[MODEL_ONBOARDING_STAGED_RECORD]
            ._stage(snapshot, (*adapter.parse(fetched, None).records, *annex))
            .filtered(lambda record: record.kind == "certificate")
        )

        self.assertEqual(second.external_key, "VILAS 9972")
        self.assertEqual(
            sorted(second.child_ids.mapped("external_key")), sorted(f"VILAS 9972: {code}" for code in SCOPE)
        )
        self.assertEqual(sorted(child.source_values["code"] for child in second.child_ids), sorted(SCOPE))
        self.assertEqual(len(first.child_ids), len(SCOPE))
        self.assertEqual(set(first.child_ids.mapped("state")), {"to_review"})
