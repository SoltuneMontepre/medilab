from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_TESTING_FIELD,
)
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import (
    ACTION_UPDATE,
    KIND_MODELS,
    STAGED_REJECTED,
    STAGED_TO_REVIEW,
    VALUE_KEYS,
)

TEXT_KEYS = ("code", "name", "issuing_body")
DATE_KEYS = ("valid_from", "valid_until")
RECORD_KEYS = ("field_id", "main_group_id", "unit_id", "department_id")
EDITABLE_KEYS = TEXT_KEYS + DATE_KEYS + RECORD_KEYS


# Bản Ghi Chờ Duyệt: what the administrator reads, edits, confirms, rejects and reopens.
class OnboardingStagedRecordReview(models.Model):
    _inherit = MODEL_ONBOARDING_STAGED_RECORD
    _rec_name = "external_key"

    # The values below show the edited value, else the source's; writing one stores it in the edited values.
    code = fields.Char(string="Code", compute="_compute_values", inverse="_inverse_values")
    name = fields.Char(string="Name", compute="_compute_values", inverse="_inverse_values")
    issuing_body = fields.Char(string="Issuing Body", compute="_compute_values", inverse="_inverse_values")
    valid_from = fields.Date(string="Valid From", compute="_compute_values", inverse="_inverse_values")
    valid_until = fields.Date(string="Valid Until", compute="_compute_values", inverse="_inverse_values")
    field_id = fields.Many2one(
        MODEL_TESTING_FIELD, string="Testing Field", compute="_compute_values", inverse="_inverse_values"
    )
    main_group_id = fields.Many2one(
        MODEL_PARAMETER_GROUP,
        string="Main Group",
        compute="_compute_values",
        inverse="_inverse_values",
        domain="[('child_ids', '=', False)]",
    )
    unit_id = fields.Many2one(
        MODEL_MEASUREMENT_UNIT, string="Unit", compute="_compute_values", inverse="_inverse_values"
    )
    department_id = fields.Many2one(
        MODEL_DEPARTMENT,
        string="Department",
        compute="_compute_values",
        inverse="_inverse_values",
        domain=DEPARTMENT_DOMAIN,
    )
    # One "Label: value" line per value the source gave.
    source_summary = fields.Text(string="Source Values Summary", compute="_compute_source_summary")
    # For an update, one "field: current → new" line per value that differs from the matched record.
    changes = fields.Text(string="Changes", compute="_compute_changes")
    # The Laboratory record it matches or became; setting it confirms the match.
    match_ref = fields.Reference(
        selection="_match_selection", string="Match", compute="_compute_match_ref", inverse="_inverse_match_ref"
    )

    @api.model
    def _match_selection(self):
        return [(model, self.env["ir.model"]._get(model).display_name) for model in KIND_MODELS.values()]

    def _value_labels(self) -> dict:
        _ = self.env._
        return {
            "code": _("Code"),
            "name": _("Name"),
            "issuing_body": _("Issuing Body"),
            "valid_from": _("Valid From"),
            "valid_until": _("Valid Until"),
            "field_key": _("Testing Field Key"),
            "parameter_key": _("Parameter Key"),
            "method_key": _("Method Key"),
        }

    @api.depends("source_values", "edited_values")
    def _compute_values(self):
        for record in self:
            values = record._effective_values()
            for key in TEXT_KEYS:
                record[key] = values.get(key) or False
            for key in DATE_KEYS:
                record[key] = fields.Date.to_date(values.get(key) or False)
            for key in RECORD_KEYS:
                comodel = self.env[self._fields[key].comodel_name]
                record[key] = comodel.browse(values.get(key) or []).exists()

    def _inverse_values(self):
        for record in self:
            edited = {}
            for key in EDITABLE_KEYS:
                value = record[key]
                if key in RECORD_KEYS:
                    value = value.id
                elif key in DATE_KEYS:
                    value = value.isoformat() if value else ""
                value = value or ""
                if value != (record.source_values.get(key) or ""):
                    edited[key] = value
            record.edited_values = edited or False

    @api.depends("source_values", "kind")
    def _compute_source_summary(self):
        labels = self._value_labels()
        for record in self:
            record.source_summary = "\n".join(
                f"{labels[key]}: {record.source_values.get(key) or ''}" for key in VALUE_KEYS[record.kind]
            )

    @api.depends("source_values", "edited_values", "record_model", "record_id", "action", "lang")
    def _compute_changes(self):
        labels = self._value_labels()
        for record in self:
            differences = []
            if record.action == ACTION_UPDATE and record.record_id:
                differences = record._differences(record.record_model, record.record_id)
            record.changes = "\n".join(f"{labels[key]}: {current} → {wanted}" for key, current, wanted in differences)

    @api.depends("record_model", "record_id")
    def _compute_match_ref(self):
        for record in self:
            record.match_ref = f"{record.record_model},{record.record_id}" if record.record_id else False

    def _inverse_match_ref(self):
        for record in self:
            matched = record.match_ref
            if matched and matched._name != KIND_MODELS[record.kind]:
                raise ValidationError(
                    self.env._("The match must be a record of the model of the kind %s.", record.kind)
                )
            model, matched_id = (matched._name, matched.id) if matched else (False, 0)
            record.write(
                {
                    "record_model": model,
                    "record_id": matched_id,
                    "match_suggested": False,
                    "action": record._proposed_action(model, matched_id),
                }
            )

    def _check_to_review(self):
        self._check_permission("edit")
        if self.filtered(lambda record: record.state != STAGED_TO_REVIEW):
            raise UserError(self.env._("Only staged records to review can be rejected or have their match confirmed."))

    def action_confirm_match(self):
        self._check_to_review()
        self.write({"match_suggested": False})

    def action_reject(self, reason):
        self._check_to_review()
        self.write(
            {
                "state": STAGED_REJECTED,
                "reject_reason": reason,
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            }
        )

    def action_reopen(self):
        self._check_permission("edit")
        if self.filtered(lambda record: record.state != STAGED_REJECTED):
            raise UserError(self.env._("Only rejected staged records can be reopened."))
        self.write({"state": STAGED_TO_REVIEW, "reject_reason": False, "reviewed_by_id": False, "reviewed_at": False})
