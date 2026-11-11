from odoo.fields import Command

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id


class RequestCase(MasterDataCase):
    """A customer's test request created without an order, with one bottled water sample tested for lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env[MODEL_CUSTOMER].create({"name": "An Phu Beverage Co., Ltd.", "is_company": True})
        cls.sample_type = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Bottled drinking water"})
        cls.applicability = cls.offer(cls.parameter, cls.sample_type)
        cls.request = cls.create_request()
        cls.sample = cls.request.sample_ids

    @classmethod
    def create_request(cls):
        return cls.env[MODEL_TEST_REQUEST].create(
            {
                "customer_id": cls.customer.id,
                "expected_date": "2026-10-20",
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": "Lavie bottled water 1 L",
                            "sample_type_id": cls.sample_type.id,
                            "physical_state": "liquid",
                            "test_ids": [Command.create({"parameter_id": cls.parameter.id})],
                        }
                    )
                ],
            }
        )

    def head_of(self, department):
        """A person who manages the department and may edit samples."""
        head = self.env[MODEL_PERSON].create(
            {
                "name": "Le Thi Hoa",
                "login": "hoa.head",
                "department_id": department.id,
                "permission_ids": [
                    Command.set(
                        [
                            persisted_id(
                                reference_as(
                                    self.env[MODEL_PERMISSION], f"sol_laboratory.permission_sample_{action}_all"
                                )
                            )
                            for action in ("read", "edit")
                        ]
                    )
                ],
            }
        )
        department.manager_id = head.employee_id
        return head
