from odoo import fields
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SECTOR,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import CRAWL_JOB
from odoo.addons.sol_onboarding.services.adapters.base import Fetched
from odoo.addons.sol_onboarding.services.adapters.registry import adapter_for
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

BAM = "https://www.fda.gov/food/laboratory-methods-food/bacteriological-analytical-manual-bam"


def recorded(name):
    with file_open(f"sol_onboarding/tests/pages/fda/{name}", "rb") as page:
        return page.read()


@tagged("post_install", "-at_install")
class TestFdaBamAdapter(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fda = (
            cls.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .create(
                {
                    "name": "FDA BAM",
                    "adapter": "fda_bam",
                    "host": "www.fda.gov",
                    "start_url": BAM,
                    "delay_seconds": 30,
                    "enabled": True,
                }
            )
        )

    def test_stages_the_current_chapters_under_microbiology(self):
        fetched = Fetched(BAM, "html", recorded("bam.html"), fields.Datetime.now())
        parsed = adapter_for(self.fda).parse(fetched, "food")
        field, *methods = parsed.records
        self.assertEqual(
            (field.kind, field.key, field.values, field.lang, field.sector),
            ("testing_field", "Microbiology", {"code": "", "name": "Microbiology"}, "en_US", "food"),
        )
        self.assertEqual(
            [(m.key, m.values) for m in methods],
            [
                (f"FDA BAM Ch. {number}", {"code": f"FDA BAM Ch. {number}", "name": title, "field_key": "Microbiology"})
                for number, title in (
                    ("1", "Food Sampling and Preparation of Sample Homogenate"),
                    ("4A", "Diarrheagenic Escherichia coli"),
                    ("5", "Salmonella"),
                    ("23", "Microbiological Methods for Cosmetics"),
                )
            ],
        )
        self.assertEqual(
            {(m.kind, m.parent, m.sector, m.lang) for m in methods}, {("testing_method", None, "food", "en_US")}
        )
        self.assertEqual(parsed.links, ())

    def test_reads_one_page_for_food_and_cosmetics_and_lists_no_organisations(self):
        adapter = adapter_for(self.fda)
        self.assertEqual(adapter.sectors, ("food", "cosmetics"))
        self.assertEqual(adapter.sector_pages("cosmetics"), [BAM])
        self.assertEqual(adapter.organisation_list_pages(), [])

    def test_a_run_for_food_and_cosmetics_fetches_the_manual_once(self):
        self.source.enabled = False
        calls = self.serve({BAM: (200, "text/html; charset=UTF-8", recorded("bam.html"), {})})
        sectors = self.env[MODEL_ONBOARDING_SECTOR].search([("code", "in", ["food", "cosmetics"])])
        run = self.env[MODEL_ONBOARDING_RUN].with_user(self.admin).create({"sector_ids": sectors.ids})
        run.action_start()
        self.run_until_settled(CRAWL_JOB)

        self.assertEqual([call.url for call in calls].count(BAM), 1)
        self.assertEqual((run.sudo().state, len(run.sudo().staged_record_ids)), ("done", 5))
