from odoo.tests import TransactionCase

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
)


class MasterDataCase(TransactionCase):
    """A unit, a method, a group and a parameter tested by one way of testing, offered on no sample type yet."""

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
                "department_id": cls.department.id,
            }
        )

    @classmethod
    def offer(cls, parameter, sample_type, way=None, **vals):
        """Make a way of testing of the parameter apply to the sample type in the case's unit: the given way, or else the
        parameter's first, created in the case's department when it has none. The first way offered on a sample type
        becomes its default."""
        if not way:
            way = parameter.method_ids[:1] or cls.env[MODEL_PARAMETER_METHOD].create(
                {"parameter_id": parameter.id, "method_id": cls.method.id, "department_id": cls.department.id}
            )
        return cls.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].create(
            {
                "parameter_method_id": way.id,
                "sample_type_id": sample_type.id,
                "unit_id": cls.unit.id,
                "is_default": not parameter._default_way(sample_type),
                **vals,
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
