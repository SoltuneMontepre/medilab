from collections import defaultdict

import psycopg2

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import format_list, mute_logger

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)
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
from odoo.addons.sol_onboarding.models.onboarding.onboarding_staged_record_matching import normalize_code

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
        # Certificates go first, so the methods of their scope are accepted with them.
        for record in self.sorted(lambda record: record.kind != KIND_CERTIFICATE):
            # Accepted already, as a record that one before it needs.
            if record in to_review and record.state == STAGED_ACCEPTED:
                continue
            try:
                with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
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
        user, in the user's language."""
        self.ensure_one()
        _ = self.env._
        if self.state != STAGED_TO_REVIEW:
            raise UserError(_("Only staged records to review can be accepted."))
        if self.match_suggested:
            raise UserError(_("Confirm or clear the suggested match of %s first.", self._describe()))
        model = self.env[KIND_MODELS[self.kind]]
        for field, need in self._needs().items():
            if need.state == STAGED_TO_REVIEW:
                need._accept_one()
            elif not need and field not in ASKED_KEYS.get(self.kind, ()):
                self._refuse_need(model._fields[field])
        if missing := self._own_missing_values():
            labels = [self._fields[key]._description_string(self.env) for key in missing]
            raise UserError(
                _(
                    "%(record)s needs these values first: %(values)s.",
                    record=self._describe(),
                    values=format_list(self.env, labels),
                )
            )
        record = self._accept_certificate(model) if self.kind == KIND_CERTIFICATE else self._laboratory_record(model)
        self._mark_accepted(record)
        parent = self.parent_id
        if self.kind == KIND_TESTING_METHOD and parent.kind == KIND_CERTIFICATE and parent.state == STAGED_ACCEPTED:
            # Methods refuse certificate_ids, so the certificate links the method.
            self.env[MODEL_ACCREDITATION_CERTIFICATE].browse(parent.record_id).exists().write(
                {"method_ids": [Command.link(record.id)]}
            )

    def _mark_accepted(self, record):
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

    def _refuse_need(self, field):
        label = field._description_string(self.env)
        raise UserError(
            self.env._(
                "The staged %(need)s that %(record)s needs is neither to review nor accepted.",
                need=label,
                record=self._describe(),
            )
        )

    def _accept_certificate(self, model):
        """Create, link or update the certificate, link the methods of its scope accepted before it, then link the
        to-review ones through Laboratory's import, one import per testing field. Methods whose codes differ only in
        case and spaces make one line, under a matched method's own code, so the import links it however the source
        wrote the code. The methods to create or link are accepted with the certificate; one to update is linked but
        stays to review, so its changes are accepted on their own."""
        _ = self.env._
        certificate = self._laboratory_record(model)
        accepted = self.child_ids.filtered(
            lambda child: child.kind == KIND_TESTING_METHOD and child.state == STAGED_ACCEPTED
        )
        if linked := self.env[MODEL_TESTING_METHOD].browse(accepted.mapped("record_id")).exists():
            certificate.write({"method_ids": [Command.link(method.id) for method in linked]})
        methods = self._scope_methods()
        groups = defaultdict(self.browse)
        for method in methods:
            groups[normalize_code(method.code or "")] |= method
        codes = {}
        lines = defaultdict(list)
        for group in groups.values():
            matched = self.env[MODEL_TESTING_METHOD]
            field = self.env[MODEL_TESTING_FIELD]
            for method in group:
                found = method._matched_record()
                if method.action != ACTION_CREATE and not found:
                    raise UserError(
                        _("The matched record of %s no longer exists. Set the match again.", method._describe())
                    )
                matched = matched or found
                if method.action != ACTION_UPDATE:
                    method_field = method._method_field()
                    field = field or method_field
            field = field or self.field_id or matched.field_id
            codes.update(dict.fromkeys(group, matched.code or group[0].code))
            lines[field.id].append(Command.create({"code": codes[group[0]], "name": group[0].name}))
        for field_id, field_lines in lines.items():
            self.env[MODEL_ACCREDITATION_CERTIFICATE_IMPORT].create(
                {"certificate_id": certificate.id, "field_id": field_id, "lang": self.lang, "line_ids": field_lines}
            ).action_import()
        imported = (
            self.env[MODEL_TESTING_METHOD]
            .with_context(active_test=False)
            .search([("code", "in", list(codes.values()))])
        )
        by_code = {record.code: record for record in imported}
        for method in methods.filtered(lambda method: method.action != ACTION_UPDATE):
            if codes[method] not in by_code:
                raise UserError(_("No testing method has the code %s after the import.", codes[method]))
            method._mark_accepted(by_code[codes[method]])
        return certificate

    def _scope_methods(self):
        """The staged methods of a certificate's scope that are to review, in the order they were staged."""
        if self.kind != KIND_CERTIFICATE:
            return self.browse()
        return self.child_ids.filtered(
            lambda child: child.kind == KIND_TESTING_METHOD and child.state == STAGED_TO_REVIEW
        ).sorted("id")

    def _method_field(self):
        """The testing field of a staged method: the edited one, else the one its staged testing field became, which
        is accepted first when still to review. Empty when it has neither. A method to create refuses a staged testing
        field that the source names but that is neither to review nor accepted."""
        needs = self._needs()
        need = needs.get("field_id", self.browse())
        if need.state == STAGED_TO_REVIEW:
            need._accept_one()
        elif "field_id" in needs and not need and self.action == ACTION_CREATE and self._field_named():
            self._refuse_need(self._fields["field_id"])
        return self.field_id or self.env[MODEL_TESTING_FIELD].browse(need.record_id)

    def _field_named(self) -> bool:
        return bool(self._effective_values().get("field_key"))

    def _laboratory_record(self, model):
        """Create the record, or link or update the matched one, writing only the values that differ. The name is
        written in the staged language, the other values in the user's. Active is never written, so an archived record
        stays archived."""
        if self.action == ACTION_CREATE:
            values = self._laboratory_values()
            if values.get("name"):
                # As a create in the staged language stores it: in that language and as the source text.
                values["name"] = {"en_US": values["name"], self.lang: values["name"]}
            return model.create(values)
        record = self._matched_record().with_env(model.env)
        if not record:
            raise UserError(self.env._("The matched record no longer exists. Set the match again."))
        if self.action == ACTION_UPDATE:
            values = self._laboratory_values()
            changed = {key: values[key] for key, _current, _wanted in self._differences(record.id)}
            record.write({key: value for key, value in changed.items() if key != "name"})
            if "name" in changed:
                record.with_context(lang=self.lang).write({"name": changed["name"]})
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
        """The asked keys a record to create has no value for; a staged record that a need names gives its key. A
        certificate misses the testing field when a method of its scope to create misses one, and gives it to them."""
        self.ensure_one()
        if self.kind == KIND_CERTIFICATE:
            # A method whose source names a testing field it cannot have is refused instead.
            fieldless = any(
                method._own_missing_values() and not method._field_named() for method in self._scope_methods()
            )
            return ["field_id"] if fieldless and not self.field_id else []
        if self.action != ACTION_CREATE:
            return []
        needs = self._needs()
        return [key for key in ASKED_KEYS.get(self.kind, ()) if not self[key] and not needs.get(key)]

    def _missing_values(self) -> dict:
        """The asked keys that the record, or a to-review record it needs at any depth, has no value for, each with
        the staged record that misses it; a certificate's methods to create or link count their needs. No two records
        of one chain ask the same key."""
        self.ensure_one()
        missing = dict.fromkeys(self._own_missing_values(), self)
        needs = list(self._needs().values())
        for method in self._scope_methods().filtered(lambda method: method.action != ACTION_UPDATE):
            needs += method._needs().values()
        for need in needs:
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
