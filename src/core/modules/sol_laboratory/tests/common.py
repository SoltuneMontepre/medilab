from odoo.tests import TransactionCase

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
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
        cls.department = cls.env[MODEL_DEPARTMENT].create({"name": "Analytical chemistry"})
        cls.pair = cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cls.parameter.id,
                "method_id": cls.method.id,
                "unit_id": cls.unit.id,
                "department_id": cls.department.id,
                "is_default": True,
            }
        )

    @classmethod
    def create_parameter(cls, name, group, **vals):
        return cls.env[MODEL_TEST_PARAMETER].create(
            {"name": name, "group_ids": [group.id], "main_group_id": group.id, **vals}
        )


class UnshippedPermissionCase(TransactionCase):
    """Test parameters that also list read, delete and sign, whose permissions no module ships, so tests create them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(
            type(cls.env[MODEL_TEST_PARAMETER]),
            "_permission_actions",
            ("read", "create", "edit", "archive", "delete", "sign"),
        )
