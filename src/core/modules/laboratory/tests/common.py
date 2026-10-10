from odoo.tests import TransactionCase

from odoo.addons.laboratory.constants.models import (
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
)


class MasterDataCase(TransactionCase):
    """A unit, a method, a group and a parameter tested by one default way of testing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env[MODEL_UNIT_CATEGORY].create({"name": "Mass per mass"})
        cls.unit = cls.env[MODEL_MEASUREMENT_UNIT].create({"name": "mg/g", "category_id": cls.category.id})
        cls.testing_field = cls.env[MODEL_TESTING_FIELD].create({"code": "HHT", "name": "Chemistry"})
        cls.method = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 8126:2009", "name": "Lead by AAS", "field_id": cls.testing_field.id}
        )
        cls.group = cls.env[MODEL_PARAMETER_GROUP].create({"name": "Heavy metals"})
        cls.parameter = cls.create_parameter("Lead (Pb)", cls.group)
        cls.pair = cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cls.parameter.id,
                "method_id": cls.method.id,
                "unit_id": cls.unit.id,
                "is_default": True,
            }
        )

    @classmethod
    def create_parameter(cls, name, group, **vals):
        return cls.env[MODEL_TEST_PARAMETER].create(
            {"name": name, "group_ids": [group.id], "main_group_id": group.id, **vals}
        )
