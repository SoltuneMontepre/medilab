from odoo import fields
from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACTOR
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORGANISATION
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase


@tagged("post_install", "-at_install")
class TestSubcontractorListing(OnboardingCase):
    def subcontractor(self, number):
        return self.env[MODEL_SUBCONTRACTOR].create({"name": "Subcontractor", "accreditation_number": number})

    def list_organisation(self):
        return (
            self.env[MODEL_ONBOARDING_ORGANISATION]
            .sudo()
            .create(
                {
                    "source_id": self.source.id,
                    "external_key": "listed-laboratory",
                    "name": "Listed Laboratory",
                    "accreditation_code": "VILAS 9950",
                    "url": "https://lab.example/listed-laboratory",
                    "seen_at": fields.Datetime.now(),
                }
            )
        )

    def test_a_listed_number_names_its_organisation(self):
        self.list_organisation()

        subcontractor = self.subcontractor("vilas  9950")

        self.assertEqual(
            (subcontractor.accreditation_listed, subcontractor.accreditation_listing),
            (True, "Listed as Listed Laboratory."),
        )

    def test_an_unlisted_number_is_said_to_be_unlisted(self):
        self.list_organisation()

        subcontractor = self.subcontractor("VILAS 0000")

        self.assertEqual(
            (subcontractor.accreditation_listed, subcontractor.accreditation_listing),
            (False, "No listed organisation has this accreditation number."),
        )

    def test_nothing_is_said_without_a_number_or_a_list(self):
        self.assertFalse(self.subcontractor("VILAS 9950").accreditation_listing)
        self.list_organisation()
        self.assertFalse(self.subcontractor(False).accreditation_listing)
