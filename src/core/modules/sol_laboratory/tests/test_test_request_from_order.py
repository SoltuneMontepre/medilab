from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST


@tagged("post_install", "-at_install")
class TestTestRequestFromOrder(RequestCase):
    def _order_samples(self, lines):
        return [
            {
                "customer_sample_name": "Bottled water",
                "sample_type_id": self.sample_type.id,
                "physical_state": "liquid",
                "lines": lines,
            }
        ]

    def test_a_package_line_becomes_one_sample_test_per_parameter(self):
        other = self.create_parameter("pH", self.group)
        request = self.env[MODEL_TEST_REQUEST].create_from_order(
            self.customer,
            [
                {
                    "customer_sample_name": "Bottled water",
                    "sample_type_id": self.sample_type.id,
                    "physical_state": "liquid",
                    "lines": [
                        {
                            "parameters": [
                                {"parameter_id": self.parameter.id},
                                {"parameter_id": other.id, "quantity": 2},
                            ]
                        }
                    ],
                },
                {
                    "customer_sample_name": "Cabbage",
                    "sample_type_id": self.sample_type.id,
                    "physical_state": "solid",
                    "lines": [{"parameter_id": self.parameter.id}],
                },
            ],
            expected_date="2026-10-20",
            report_language="vi",
            delivery_method="email",
        )

        self.assertEqual(request.status, "draft")
        self.assertEqual(request.report_language, "vi")
        bottled = request.sample_ids.filtered(lambda sample: sample.customer_sample_name == "Bottled water")
        self.assertEqual(set(bottled.test_ids.mapped("parameter_id")), {self.parameter, other})
        self.assertEqual(bottled.test_ids.filtered(lambda test: test.parameter_id == other).quantity, 2)
        cabbage = request.sample_ids.filtered(lambda sample: sample.customer_sample_name == "Cabbage")
        self.assertEqual(cabbage.test_ids.parameter_id, self.parameter)

    def test_an_unpaid_order_without_credit_cannot_be_confirmed(self):
        request = self.env[MODEL_TEST_REQUEST].create_from_order(
            self.customer,
            self._order_samples([{"parameter_id": self.parameter.id}]),
        )

        with (
            patch.object(type(request), "_credit_blocks_confirmation", lambda self: True),
            self.assertRaises(UserError),
        ):
            request.action_confirm()
        self.assertEqual(request.status, "draft")

    def test_credit_lets_an_order_request_be_confirmed(self):
        request = self.env[MODEL_TEST_REQUEST].create_from_order(
            self.customer,
            self._order_samples([{"parameter_id": self.parameter.id}]),
        )

        request.action_confirm()
        self.assertEqual(request.status, "confirmed")
