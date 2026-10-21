import psycopg2

from odoo import Command, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import (
    ACTION_CREATE,
    ACTION_UPDATE,
    ASKED_KEYS,
    KIND_CERTIFICATE,
    KIND_MODELS,
    KIND_NEEDS,
    KIND_PARAMETER_METHOD,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_FIELD,
    KIND_TESTING_METHOD,
    STAGED_ACCEPTED,
    STAGED_TO_REVIEW,
)
from odoo.addons.sol_onboarding.constants.xml_ids import ACCEPT_ACTION

# Values a Laboratory record of each kind takes from the staged value field of the same name.
LABORATORY_KEYS = {
    KIND_CERTIFICATE: ("code", "issuing_body", "valid_from", "valid_until"),
    KIND_TESTING_FIELD: ("code", "name"),
    KIND_TESTING_METHOD: ("code", "name", "field_id"),
    KIND_SAMPLE_TYPE: ("name",),
    KIND_TEST_PARAMETER: ("name", "main_group_id"),
    KIND_PARAMETER_METHOD: ("unit_id", "department_id"),
}
# The Laboratory field each need key fills with the record its staged record became.
NEED_FIELDS = {"field_key": "field_id", "parameter_key": "parameter_id", "method_key": "method_id"}


# Bản Ghi Chờ Duyệt: accepting turns it into Laboratory master data.
class OnboardingStagedRecordAcceptance(models.Model):
    _inherit = MODEL_ONBOARDING_STAGED_RECORD

    def action_accept(self):
        """Accept the records, or ask for the values one record misses. The result lists the refused records."""
        self._check_permission("edit")
        if len(self) == 1 and self._missing_values():
            action = self.env["ir.actions.act_window"]._for_xml_id(ACCEPT_ACTION)
            action["context"] = {"default_staged_record_id": self.id}
            return action
        refused = self._accept_each()
        if refused:
            return {
                "type": "ir.actions.act_window",
                "name": self.env._("Refused Staged Records"),
                "res_model": MODEL_ONBOARDING_STAGED_RECORD,
                "views": [(False, "list"), (False, "form")],
                "domain": [("id", "in", refused.ids)],
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Staged records accepted: %s.", len(self)),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _accept_each(self):
        """Accept each record in a savepoint with the records it needs, so a refusal leaves it and them to review and
        keeps the others. A UserError, which ValidationError and AccessError are, or a refused database constraint
        refuses a record. Returns the refused records, each with its error."""
        refused = self.browse()
        to_review = self.filtered(lambda record: record.state == STAGED_TO_REVIEW)
        for record in self:
            # Accepted already, as a record that one before it needs.
            if record in to_review and record.state == STAGED_ACCEPTED:
                continue
            try:
                with self.env.cr.savepoint():
                    record._accept_one()
            except psycopg2.IntegrityError as error:
                record.error = self._constraint_message(error)
                refused |= record
            except UserError as error:
                record.error = str(error)
                refused |= record
        return refused

    def _constraint_message(self, error) -> str:
        """The message of the refused constraint, from the model of its table, as Odoo gives it for a form."""
        table = error.diag.table_name
        model = next(
            (self.env[name] for name, cls in self.env.registry.items() if cls._table == table), self.env["base"]
        )
        return model._sql_error_to_message(error)

    def _accept_one(self):
        """Accept the to-review records it needs, then create, link or update its Laboratory record as the current
        user, in the staged language."""
        self.ensure_one()
        _ = self.env._
        if self.state != STAGED_TO_REVIEW:
            raise UserError(_("Only staged records to review can be accepted."))
        if self.match_suggested:
            raise UserError(_("Confirm or clear the suggested match first."))
        model = self.env[KIND_MODELS[self.kind]].with_context(lang=self.lang)
        for field, need in self._needs().items():
            if need.state == STAGED_TO_REVIEW:
                need._accept_one()
            elif not need and field not in ASKED_KEYS.get(self.kind, ()):
                label = model._fields[field]._description_string(self.env)
                raise UserError(_("The staged %s it needs is neither to review nor accepted.", label))
        if missing := self._own_missing_values():
            labels = [self._fields[key]._description_string(self.env) for key in missing]
            raise UserError(
                _(
                    "%(record)s needs these values first: %(values)s.",
                    record=self._describe(),
                    values=format_list(self.env, labels),
                )
            )
        record = self._laboratory_record(model)
        self.write(
            {
                "state": STAGED_ACCEPTED,
                "record_model": record._name,
                "record_id": record.id,
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
                "error": False,
            }
        )

    def _laboratory_record(self, model):
        """Create the record, or link or update the matched one, writing only the values that differ. Active is never
        written, so an archived record stays archived."""
        if self.action == ACTION_CREATE:
            return model.create(self._laboratory_values())
        record = self._matched_record().with_env(model.env)
        if not record:
            raise UserError(self.env._("The matched record no longer exists. Set the match again."))
        if self.action == ACTION_UPDATE:
            values = self._laboratory_values()
            record.write({key: values[key] for key, _current, _wanted in self._differences(record._name, record.id)})
        return record

    def _needs(self) -> dict:
        """The staged record each need names, by the Laboratory field it fills; an edited value takes its place."""
        values = self._effective_values()
        needs = {}
        for key, kind in KIND_NEEDS.get(self.kind, {}).items():
            field = NEED_FIELDS[key]
            if not values.get(field):
                needs[field] = self._resolve_need(kind, values.get(key) or "").with_env(self.env)
        return needs

    def _own_missing_values(self) -> list[str]:
        """The asked keys a record to create has no value for; a staged record that a need names gives its key."""
        self.ensure_one()
        if self.action != ACTION_CREATE:
            return []
        needs = self._needs()
        return [key for key in ASKED_KEYS.get(self.kind, ()) if not self[key] and not needs.get(key)]

    def _missing_values(self) -> dict:
        """The asked keys that the record, or a to-review record it needs at any depth, has no value for, each with
        the staged record that misses it. No two records of one chain ask the same key."""
        self.ensure_one()
        missing = dict.fromkeys(self._own_missing_values(), self)
        for need in self._needs().values():
            if need.state == STAGED_TO_REVIEW:
                missing.update(need._missing_values())
        return missing

    def _describe(self) -> str:
        """The kind and the value of the record, such as "Test Parameter pH"."""
        kind = dict(self._fields["kind"]._description_selection(self.env))[self.kind]
        return f"{kind} {self.display_value or self.external_key}"

    def _laboratory_values(self) -> dict:
        """The values of its Laboratory record: the shown values, and the record each need became."""
        self.ensure_one()
        values = {key: self._fields[key].convert_to_write(self[key], self) for key in LABORATORY_KEYS[self.kind]}
        values.update({field: need.record_id for field, need in self._needs().items()})
        if self.kind == KIND_TEST_PARAMETER:
            values["group_ids"] = [Command.set([values["main_group_id"]])]
        return values
