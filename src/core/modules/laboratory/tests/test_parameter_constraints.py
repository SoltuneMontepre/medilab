from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.laboratory.constants.models import MODEL_TEST_PARAMETER


@tagged("post_install", "-at_install")
class TestParameterConstraints(TransactionCase):
    def test_code_is_unique(self):
        self.env[MODEL_TEST_PARAMETER].create({"code": "WBC", "name": "White blood cells"})

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_TEST_PARAMETER].create({"code": "WBC", "name": "Duplicate"})

    def test_parameters_are_ordered_by_code(self):
        model = self.env[MODEL_TEST_PARAMETER]
        model.create([{"code": "RBC", "name": "Red blood cells"}, {"code": "HGB", "name": "Hemoglobin"}])

        codes = model.search([("code", "in", ["RBC", "HGB"])]).mapped("code")

        self.assertEqual(codes, ["HGB", "RBC"])
