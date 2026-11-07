from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_RES_LANG,
    MODEL_SAMPLE_TYPE,
    MODEL_SAMPLING_REQUIREMENT,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestSamplingRequirements(MasterDataCase):
    """The case's method and a coliform method sampled on bottled water."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env[MODEL_RES_LANG]._activate_lang("vi_VN")
        cls.water = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled water"})
        cls.coliforms = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6187-2:1996", "name": "Coliforms by MPN", "field_id": cls.testing_field.id}
        )

    def require(self, method=None, **vals):
        return self.env[MODEL_SAMPLING_REQUIREMENT].create(
            {
                "method_id": (method or self.method).id,
                "sample_type_id": self.water.id,
                "amount": 500,
                "unit_id": self.unit.id,
                "container_type": "Polyethylene bottle",
                "preservation": "Acidified with HNO3",
                **vals,
            }
        )

    def refusal(self, **vals):
        """The message a user gets when the database refuses the requirement."""
        with self.assertRaises(IntegrityError) as refused, mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.require(**vals)
            self.env.flush_all()
        return self.env[MODEL_SAMPLING_REQUIREMENT]._sql_error_to_message(refused.exception)

    def test_a_method_lists_its_requirements(self):
        requirement = self.require()

        self.assertEqual(self.method.sampling_requirement_ids, requirement)

    def test_a_method_has_one_requirement_per_sample_type(self):
        self.require()

        self.assertIn("only one sampling requirement", self.refusal())

    def test_the_amount_must_be_above_zero(self):
        self.assertIn("must be above 0", self.refusal(amount=0))

    def test_translations_do_not_split_a_group(self):
        lead = self.require()
        coliforms = self.require(self.coliforms, amount=250)
        lead.update_field_translations("container_type", {"vi_VN": "Chai PE"})
        coliforms.update_field_translations("container_type", {"vi_VN": "Chai nhựa PE"})

        rows, missing = self.env[MODEL_SAMPLING_REQUIREMENT]._sampling_rows(self.water, self.method | self.coliforms)

        self.assertFalse(missing)
        self.assertEqual([(row["group"], row["amount"]) for row in rows], [(1, 750)])

    def test_a_narrower_type_does_not_share_its_parent_requirements(self):
        self.require()
        child = self.env[MODEL_SAMPLE_TYPE].create({"name": "Mineral water", "parent_id": self.water.id})

        rows, missing = self.env[MODEL_SAMPLING_REQUIREMENT]._sampling_rows(child, self.method)

        self.assertEqual(rows, [])
        self.assertEqual(missing, self.method)
