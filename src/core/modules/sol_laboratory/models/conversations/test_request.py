from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHATTER_MIXIN, MODEL_TEST_REQUEST

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestChatterBase
else:
    TestRequestChatterBase = object


# Yêu Cầu Thử Nghiệm: its chatter.
class TestRequestChatter(models.Model, TestRequestChatterBase):
    _name = MODEL_TEST_REQUEST
    _inherit = [MODEL_TEST_REQUEST, MODEL_CHATTER_MIXIN]
