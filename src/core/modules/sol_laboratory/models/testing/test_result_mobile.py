from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE, STATE_REQUESTED
from odoo.addons.sol_laboratory.constants.laboratory_files import PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.medilab_mobile import RESULT_WARNING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_PERSON,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_results import phone_result_values

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultMobileBase
else:
    TestResultMobileBase = object


# Kết Quả Thử Nghiệm: what Medilab Mobile reads and does with results at the bench, with the person's rights: changing
# a draft, sending or approving it, and rejecting it.
class TestResultMobile(models.Model, TestResultMobileBase):
    _name = MODEL_TEST_RESULT
    _inherit = [MODEL_TEST_RESULT, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "created_by_device_id"

    if not TYPE_CHECKING:
        # The phone the result was entered on; empty for a result entered on the web.
        created_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(created_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already entered a result with this Idempotency-Key.",
    )

    @api.model
    def _mobile_awaiting(self, offset, limit):
        """A page of the results waiting for the person's signature, oldest first, and whether another page follows.
        Whether they may sign is computed, so the results are filtered before paging."""
        waiting = self.search([("status", "=", STATE_REQUESTED)], order="entered_at, id").filtered("approval_can_sign")
        return waiting[offset : offset + limit], len(waiting) > offset + limit

    @api.model
    def _may_sign_awaiting(self):
        """Whether results can wait for the person's signature: they may sign results and hold the role of a level
        after the first, which signs the results the first level sent."""
        roles = self.env[MODEL_PERSON]._current().sudo().role_ids
        later = self._approval_chain().level_ids.sorted("sequence")[1:]
        return self._has_permission("sign") and any(level.role_id in roles for level in later)

    def _mobile_values(self):
        """The results as Medilab Mobile lists them."""
        return [
            {
                "id": result.id,
                "code": result.sudo().sample_id.code or "",
                "parameter": result.parameter_id.display_name or "",
                "value_display": result._mobile_value(),
                "unit": result.sudo().unit_id.name or "",
                "status": result.status,
                "entered_by": result.sudo().entered_by_id.name or "",
                "entered_at": api_datetime(result.entered_at),
                "warned": bool(result.check_warning),
            }
            for result in self
        ]

    def _mobile_value(self):
        """The result as shown, with its unit when it is a number."""
        unit = self.sudo().unit_id.name
        if self.value_text or not unit:
            return self.value_display or ""
        return f"{self.value_display} {unit}"

    def _mobile_detail(self):
        """The result with its limit, its warnings and what the person may do with it, as the web's form shows them."""
        self.ensure_one()
        result = self
        statuses = dict(result._fields["status"]._description_selection(self.env))
        conclusions = dict(result._fields["conclusion"]._description_selection(self.env))
        warnings = result.check_preview if result.status == STATE_NONE else result.check_warning
        return {
            **result._mobile_values()[0],
            "sample_test_id": result.sample_test_id.id,
            "way": result.sudo().parameter_method_id.display_name or "",
            "value": None if result.value_text else result.value,
            "value_text": result.value_text or "",
            "decimals": result.value_decimals,
            "value_suggestion": result.value_suggestion or "",
            "comparison_requested": result.comparison_requested,
            "conclusion": result.conclusion or None,
            "conclusion_label": conclusions.get(result.conclusion or "", ""),
            "limit": result._mobile_limit(),
            "limit_missing": result.limit_missing,
            "status_label": statuses.get(result.status or "", ""),
            "warnings": (warnings or "").splitlines(),
            "rejection_reason": result._approval_rejection_reason(),
            "actions": result._mobile_actions(),
        }

    def _mobile_limit(self):
        """The copied regulation limit as the web's form shows it, with its unit; empty without one."""
        if self.limit_text:
            return self.limit_text
        limit = self._limit_range(self.env)
        unit = self.sudo().limit_unit_id or self.sudo().unit_id
        return f"{limit} {unit.name}" if limit and unit else limit

    def _mobile_actions(self):
        """What the web's form lets the person do with the result now: change the draft, send or approve it, and
        reject it. A result that is approved, or waits for someone else's signature, takes none."""
        self.ensure_one()
        draft = self.status == STATE_NONE
        return {
            "edit": draft and bool(self._filtered_access("write")),
            "sign": self.approval_can_sign and (self.status == STATE_REQUESTED or (draft and self.is_reported)),
            "reject": self.status == STATE_REQUESTED and self.approval_can_reject,
        }

    def _change_from_phone(self, values):
        """Change the draft result as the web's form does."""
        self.ensure_one()
        if self.status != STATE_NONE:
            raise UserError(self.env._("Only a draft result can be changed; %s is not one.", self.display_name))
        try:
            self.write(phone_result_values(values))
        except AccessError as error:
            raise LaboratoryFileError(PERMISSION_DENIED, error.args[0]) from error

    def _sign_from_phone(self, values):
        """Send or approve the result as the web's form does. A draft the sanity check warns about is sent only once
        the person acknowledges its warnings."""
        self.ensure_one()
        warnings = self._check_warnings() if self.status == STATE_NONE else []
        if warnings and not values.get("warnings_acknowledged"):
            raise LaboratoryFileError(
                RESULT_WARNING,
                self.env._("Check the result before sending it: %s", " ".join(warnings)),
            )
        self.action_sign()
