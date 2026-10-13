from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_SUBCONTRACTOR

ONE_DAY = timedelta(days=1)
ONE_YEAR = timedelta(days=365)


@tagged("post_install", "-at_install")
class TestSubcontractorSelection(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env[MODEL_SUBCONTRACTOR])
        cls.accredited, cls.expired, cls.unlimited, cls.archived = cls.env[MODEL_SUBCONTRACTOR].create(
            [
                {"name": "Northern Testing Laboratory", "accreditation_expiry": cls.today + ONE_YEAR},
                {"name": "Coastal Analytical Services", "accreditation_expiry": cls.today - ONE_DAY},
                {"name": "Southern Microbiology Centre"},
                {"name": "Mekong Food Testing", "active": False},
            ]
        )

    def choose(self, subcontractor):
        return self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": subcontractor.id,
            }
        )

    def offered(self):
        # The Ways of Testing list shows archived pairs too, so its rows search subcontractors without the active test.
        field = self.env[MODEL_PARAMETER_METHOD].fields_get(["subcontractor_id"], ["domain"])["subcontractor_id"]
        return self.env[MODEL_SUBCONTRACTOR].with_context(active_test=False).search(field["domain"])

    def test_subcontractor_with_valid_or_no_expiry_date_can_be_chosen(self):
        for subcontractor in (self.accredited, self.unlimited):
            with self.subTest(subcontractor=subcontractor.name):
                self.assertEqual(self.choose(subcontractor).subcontractor_id, subcontractor)

    def test_subcontractor_expiring_today_can_still_be_chosen(self):
        self.accredited.accreditation_expiry = self.today

        self.assertFalse(self.accredited.accreditation_expired)
        self.assertEqual(self.choose(self.accredited).subcontractor_id, self.accredited)

    def test_expired_subcontractor_is_refused_with_a_message_naming_it(self):
        with self.assertRaises(ValidationError) as refusal:
            self.choose(self.expired)

        self.assertIn(self.expired.name, str(refusal.exception))

    def test_expired_subcontractor_cannot_replace_the_subcontractor_of_a_pair(self):
        pair = self.choose(self.accredited)

        with self.assertRaises(ValidationError):
            pair.subcontractor_id = self.expired

    def test_renewed_accreditation_allows_choosing_again(self):
        with self.assertRaises(ValidationError):
            self.choose(self.expired)

        self.expired.accreditation_expiry = self.today + ONE_YEAR

        self.assertFalse(self.expired.accreditation_expired)
        self.assertEqual(self.choose(self.expired).subcontractor_id, self.expired)

    def test_pair_keeps_its_subcontractor_after_the_accreditation_expires(self):
        pair = self.choose(self.accredited)

        self.accredited.accreditation_expiry = self.today - ONE_DAY
        pair.write({"lod": 0.5, "is_accredited": True})

        self.assertTrue(self.accredited.accreditation_expired)
        self.assertEqual(pair.subcontractor_id, self.accredited)
        self.assertEqual(pair.lod, 0.5)

    def test_archived_subcontractor_is_refused_with_a_message_naming_it(self):
        with self.assertRaises(ValidationError) as refusal:
            self.choose(self.archived)

        self.assertIn(self.archived.name, str(refusal.exception))

    def test_selection_list_offers_only_active_subcontractors_with_a_valid_accreditation(self):
        offered = self.offered()

        self.assertTrue(self.accredited | self.unlimited <= offered)
        self.assertFalse((self.expired | self.archived) & offered)

    def test_renewed_or_restored_subcontractor_is_offered_again(self):
        self.expired.accreditation_expiry = self.today + ONE_YEAR
        self.archived.action_unarchive()

        self.assertTrue(self.expired | self.archived <= self.offered())

    def test_accreditation_expired_filters_subcontractors(self):
        subcontractors = self.accredited | self.expired | self.unlimited
        filtered = {
            expired: self.env[MODEL_SUBCONTRACTOR].search(
                [("accreditation_expired", "=", expired), ("id", "in", subcontractors.ids)]
            )
            for expired in (True, False)
        }

        self.assertEqual(filtered[True], self.expired)
        self.assertEqual(filtered[False], self.accredited | self.unlimited)
