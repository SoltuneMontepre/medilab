import statistics
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import float_compare, formatLang

from odoo.addons.sol_laboratory.constants.approvals import STATE_APPROVED, STATE_NONE
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_TEST_RESULT
from odoo.addons.sol_laboratory.services.number_text import plain_digits, plain_number
from odoo.addons.sol_laboratory.services.translations import in_every_language

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultCheckBase
else:
    TestResultCheckBase = object

# Values and limits are compared to this many decimals, so a value exactly on the margin, such as 0.009 against 0.01
# with a 10% margin, is not pushed past it by floating-point rounding.
COMPARE_DIGITS = 12


def compare(first: float, second: float) -> int:
    return float_compare(first, second, precision_digits=COMPARE_DIGITS)


# Kết Quả Thử Nghiệm: the sanity check of a numeric result before it is sent, against the approved results of its way of
# testing on its sample type, whoever the customer, and against its regulation limit.
class TestResultCheck(models.Model, TestResultCheckBase):
    _name = MODEL_TEST_RESULT
    _inherit = MODEL_TEST_RESULT

    if not TYPE_CHECKING:
        # Why the sanity check found the value unusual when it was sent, in each language, shown to the approver; empty
        # when nothing was found.
        check_warning = fields.Text(string="Sent With Warning", readonly=True, copy=False, translate=True)
        # Why the sanity check finds the value unusual now, shown to the tester before sending; empty once it is sent.
        check_preview = fields.Text(string="Warning", compute="_compute_check_preview")

    @api.depends("value", "value_text", "value_decimals", "status", "parameter_method_id", "sample_type_id")
    @api.depends_context("lang")
    def _compute_check_preview(self):
        for result in self:
            warnings = result._check_warnings() if result.status == STATE_NONE else []
            result.check_preview = "\n".join(warnings) or False

    def action_sign(self):
        self.ensure_one()
        if self.status == STATE_NONE:
            if self.conclusion == "pass" and not self.value_text and self._outside_limits():
                raise UserError(
                    self.env._(
                        "%(value)s is outside the regulation limit, so it cannot pass; assess it as fail or "
                        "insufficient basis.",
                        value=self._shown_value(),
                    )
                )
            # The warnings found when the result is sent stay on it for the approver; sending it is the tester's call.
            warnings = in_every_language(
                self.env, lambda lang: "\n".join(self.with_context(lang=lang)._check_warnings())
            )
            self.sudo().write({"check_warning": warnings if any(warnings.values()) else False})
        return super().action_sign()

    def _check_warnings(self) -> list[str]:
        """Why the numeric result is unusual: far from the approved results of its way of testing on its sample type,
        or close to its regulation limit. A text result is not checked. The warnings never name a customer or a
        sample."""
        self.ensure_one()
        if self.value_text:
            return []
        return [warning for warning in (self._spread_warning(), *self._limit_warnings()) if warning]

    def _spread_warning(self) -> str:
        """The warning of a value further from the mean of the approved results than the spread allowed; empty with
        fewer approved results than the minimum to compare."""
        result = self.sudo()
        if not result.parameter_method_id or not result.sample_type_id:
            return ""
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        # The results of every customer are compared; only their mean and count are shown.
        approved = result.search_fetch(
            Domain("parameter_method_id", "=", result.parameter_method_id.id)
            & Domain("sample_type_id", "=", result.sample_type_id.id)
            & Domain("status", "=", STATE_APPROVED)
            & Domain("is_replaced", "=", False)
            & Domain("value_text", "=", False)
            & Domain("id", "!=", self._origin.id),
            ["value"],
        )
        if len(approved) < max(settings._get_parameter("result_check_minimum_count"), 2):
            return ""
        values = approved.mapped("value")
        mean = statistics.fmean(values)
        deviations = settings._get_parameter("result_check_deviations")
        if abs(self.value - mean) <= deviations * statistics.stdev(values):
            return ""
        return self.env._(
            "%(value)s is more than %(deviations)s standard deviations from %(mean)s, the mean of the %(count)s "
            "approved results of this way of testing on this sample type.",
            value=self._shown_value(),
            deviations=plain_number(self.env, deviations),
            mean=self._with_unit(mean, self.value_decimals, self.unit_id),
            count=len(values),
        )

    def _limit_warnings(self) -> list[str]:
        """The warnings of a value outside its copied regulation minimum or maximum, or within the margin of one."""
        if not self.comparison_requested:
            return []
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("result_check_limit_margin_percent")
        unit = self.sudo().limit_unit_id or self.sudo().unit_id
        outside = self._outside_limits()
        warnings = []
        for side, limit, converted in self._converted_limits():
            shown = {
                "value": self._shown_value(),
                "limit": self._with_unit(limit, self.limit_decimals or plain_digits(limit), unit),
            }
            if side in outside:
                message = (
                    self.env._("%(value)s is below the regulation limit %(limit)s.", **shown)
                    if side == "min"
                    else self.env._("%(value)s is above the regulation limit %(limit)s.", **shown)
                )
                warnings.append(message)
            elif compare(abs(self.value - converted), margin / 100 * abs(converted)) <= 0:
                warnings.append(
                    self.env._(
                        "%(value)s is within %(margin)s%% of the regulation limit %(limit)s.",
                        margin=plain_number(self.env, margin),
                        **shown,
                    )
                )
        return warnings

    def _converted_limits(self):
        """The copied minimum and maximum that are set and convert to the result's unit, as (side, limit, limit in the
        result's unit)."""
        limits = []
        sides = (("min", self.limit_min_set, self.limit_min), ("max", self.limit_max_set, self.limit_max))
        for side, is_set, limit in sides:
            converted = self._in_result_unit(limit) if is_set else None
            if converted is not None:
                limits.append((side, limit, converted))
        return limits

    def _outside_limits(self) -> set[str]:
        """The sides, min or max, of the copied limit that the numeric value is beyond; empty outside the requested
        comparison or for a text result."""
        if not self.comparison_requested or self.value_text:
            return set()
        return {
            side
            for side, _limit, converted in self._converted_limits()
            if compare(self.value, converted) == (-1 if side == "min" else 1)
        }

    def _in_result_unit(self, limit):
        """The copied limit in the result's unit; None when its unit does not convert to the result's."""
        limit_unit, unit = self.sudo().limit_unit_id, self.sudo().unit_id
        if not limit_unit or not unit or limit_unit == unit:
            return limit
        if limit_unit.category_id != unit.category_id:
            return None
        return limit * limit_unit.factor / unit.factor

    def _shown_value(self):
        """The value with its unit and at least the decimals it was measured with, so a value close to a limit is not
        rounded onto it."""
        return self._with_unit(self.value, max(self.value_decimals, plain_digits(self.value)), self.unit_id)

    def _with_unit(self, number, digits, unit):
        shown = formatLang(self.env, number, digits=digits, rounding_method="HALF-UP")
        return f"{shown} {unit.sudo().name}" if unit else shown
