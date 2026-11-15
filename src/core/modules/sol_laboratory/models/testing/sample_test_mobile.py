from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import AccessError

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.laboratory_files import IDEMPOTENCY_CONFLICT, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_results import phone_result_values

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestMobileBase
else:
    SampleTestMobileBase = object


# Phép Thử Của Mẫu: what Medilab Mobile reads of a sample test at the bench, and the result the person enters on it with
# their rights; a phone enters a result once per Idempotency-Key.
class SampleTestMobile(models.Model, SampleTestMobileBase):
    _name = MODEL_SAMPLE_TEST
    _inherit = MODEL_SAMPLE_TEST

    def _mobile_detail(self):
        """The test with its lab code, parameter, way of testing and due date, the unit and decimals of the way on the
        sample's type, whether the sample's regulation is compared, and its reported result."""
        self.ensure_one()
        test = self
        # The way and the regulation are read with full rights, as the web's result form shows them to a tester. Until
        # a way is chosen, a result is entered by the parameter's default way on the sample's type.
        sample = test.sudo().sample_id
        way = test.sudo().parameter_method_id or test.sudo().parameter_id._default_way(sample.sample_type_id)
        applicability = (
            way._applicability(sample.sample_type_id) if way else self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE]
        )
        statuses = dict(test._fields["status"]._description_selection(self.env))
        reported = test._reported_result()
        return {
            "id": test.id,
            "code": sample.code or "",
            "parameter": test.parameter_id.display_name or "",
            "way": way.display_name or "",
            "due_date": api_datetime(test.due_date),
            "status": statuses.get(test.status or "", ""),
            "unit": applicability.unit_id.name or "",
            "decimals": applicability.result_decimals,
            "regulation": sample.regulation_id.display_name or "",
            "comparison_requested": test._comparison_requested(),
            "can_enter_result": test._may_enter_from_phone(reported),
            "result": reported._mobile_detail() if reported else None,
        }

    def _reported_result(self):
        """The result reported for the test, as the person may read it; none when there is none or they may not."""
        self.ensure_one()
        return self.env[MODEL_TEST_RESULT].search(
            [("sample_test_id", "=", self.id), ("is_reported", "=", True), ("is_replaced", "=", False)], limit=1
        )

    def _may_enter_from_phone(self, reported):
        """Whether the person may enter a result now, as the web's Enter Result button lets them: the test takes one and
        has no draft reported result, which the person changes instead."""
        return (
            self.can_enter_result
            and self.env[MODEL_TEST_RESULT]._has_permission("create")
            and not (reported and reported.status == STATE_NONE)
        )

    def _enter_from_phone(self, device, values, key=None):
        """The person's result for the test, entered on the phone. A request repeated with its Idempotency-Key gets
        the result it entered."""
        self.ensure_one()
        results = self.env[MODEL_TEST_RESULT]
        entered = phone_result_values(values)
        created = results._created_with_key(device, key)
        if created:
            if created.sample_test_id != self or any(
                (created[name] or False) != (value or False) for name, value in entered.items()
            ):
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return created
        try:
            return results._create_once(device, key, {"sample_test_id": self.id, **entered})
        except AccessError as error:
            raise LaboratoryFileError(PERMISSION_DENIED, error.args[0]) from error
