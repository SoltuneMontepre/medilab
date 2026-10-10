from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_GROUP,
    MODEL_QUALITY_REGISTRATION,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
)


@tagged("post_install", "-at_install")
class TestCodeSequences(MasterDataCase):
    def test_empty_code_is_filled_from_sequence(self):
        records = {
            "NCT.": self.env[MODEL_PARAMETER_GROUP].create({"name": "Pesticides"}),
            "LM.": self.env[MODEL_SAMPLE_TYPE].create({"name": "Food"}),
            "CT.": self.create_parameter("Cadmium (Cd)", self.group),
            "HS.": self.env[MODEL_QUALITY_REGISTRATION].create({"name": "Food testing registration"}),
            "TP.": self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"}),
        }

        for prefix, record in records.items():
            with self.subTest(model=record._name):
                self.assertRegex(record.code, rf"^{prefix}\d{{4}}$")

    def test_typed_code_is_kept(self):
        group = self.env[MODEL_PARAMETER_GROUP].create({"code": "PEST", "name": "Pesticides"})

        self.assertEqual(group.code, "PEST")

    def test_existing_code_is_refused(self):
        for model, vals in [
            (MODEL_PARAMETER_GROUP, {"name": "Duplicate"}),
            (MODEL_SAMPLE_TYPE, {"name": "Duplicate"}),
            (MODEL_QUALITY_REGISTRATION, {"name": "Duplicate"}),
            (MODEL_SUBCONTRACTOR, {"name": "Duplicate"}),
        ]:
            with self.subTest(model=model):
                existing = self.env[model].create(dict(vals))

                with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                    self.env[model].create({**vals, "code": existing.code})
