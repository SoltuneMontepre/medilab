from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.laboratory.constants.models import MODEL_REGULATION, MODEL_REGULATION_LIMIT


@tagged("post_install", "-at_install")
class TestRegulationConstraints(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {"code": "QCVN 8-2:2011/BYT", "name": "Bottled drinking waters"}
        )

    def create_limit(self, **vals):
        return self.env[MODEL_REGULATION_LIMIT].create(
            {"regulation_id": self.regulation.id, "parameter_id": self.parameter.id, **vals}
        )

    def test_one_limit_per_parameter(self):
        self.create_limit(max_value=0.01, unit_id=self.unit.id)

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_limit(limit_text="Not detected")

    def test_limit_needs_a_minimum_a_maximum_or_a_text(self):
        with self.assertRaises(ValidationError):
            self.create_limit(unit_id=self.unit.id)

    def test_numeric_limit_needs_a_unit(self):
        with self.assertRaises(ValidationError):
            self.create_limit(max_value=0.01)

    def test_minimum_above_maximum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create_limit(min_value=8.5, max_value=6.5, unit_id=self.unit.id)

    def test_text_limit_needs_no_unit(self):
        limit = self.create_limit(limit_text="Not detected")

        self.assertEqual(self.regulation.limit_ids, limit)
