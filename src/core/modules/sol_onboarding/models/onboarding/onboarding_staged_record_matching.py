import unicodedata

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import (
    ACTION_CREATE,
    ACTION_LINK,
    ACTION_UPDATE,
    KIND_CERTIFICATE,
    KIND_MODELS,
    KIND_NEEDS,
    KIND_PARAMETER_METHOD,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_FIELD,
    KIND_TESTING_METHOD,
    NAME_MATCH_THRESHOLD,
    STAGED_ACCEPTED,
    STAGED_TO_REVIEW,
)
from odoo.addons.sol_onboarding.services.parsing import clean_text

# Kinds that match by code.
CODE_KINDS = (KIND_CERTIFICATE, KIND_TESTING_METHOD)
# Values that decide between linking a record and updating it; a method's testing field does not count.
COMPARED_KEYS = {
    KIND_CERTIFICATE: ("code", "issuing_body", "valid_from", "valid_until"),
    KIND_TESTING_FIELD: ("code", "name"),
    KIND_TESTING_METHOD: ("code", "name"),
    KIND_SAMPLE_TYPE: ("name",),
    KIND_TEST_PARAMETER: ("name",),
}


# Folds compatibility forms, such as full-width digits, only for comparing; staged values keep the source's characters.
def normalize_code(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", clean_text(value)).split()).lower()


def is_iso_date(value: str) -> bool:
    try:
        fields.Date.to_date(value)
    except ValueError:
        return False
    return True


# Bản Ghi Chờ Duyệt: the Laboratory record a staged record matches and the action it proposes.
class OnboardingStagedRecordMatching(models.Model):
    _inherit = MODEL_ONBOARDING_STAGED_RECORD

    def write(self, vals):
        result = super().write(vals)
        if "edited_values" in vals and not {"record_model", "record_id", "match_ref"} & set(vals):
            self._match()
        return result

    @api.constrains("record_model", "kind")
    def _check_record_model(self):
        for record in self:
            if record.record_model and record.record_model != KIND_MODELS[record.kind]:
                raise ValidationError(
                    self.env._("The matched record of %s must be a record of its kind.", record._describe())
                )

    def _effective_values(self) -> dict:
        self.ensure_one()
        return {**self.source_values, **(self.edited_values or {})}

    def _resolve_need(self, kind: str, key: str):
        """The newest staged record of the kind and key from the same source, to review or accepted."""
        self.ensure_one()
        return self.sudo().search(
            [
                ("source_id", "=", self.sudo().source_id.id),
                ("kind", "=", kind),
                ("external_key", "=", key),
                ("state", "in", (STAGED_TO_REVIEW, STAGED_ACCEPTED)),
            ],
            order="id desc",
            limit=1,
        )

    def _match(self):
        """Set the match and the proposed action of each record. A way of testing goes last, since it reads the
        matches of its parameter and method."""
        for record in self.sorted(lambda staged: staged.kind == KIND_PARAMETER_METHOD):
            model, matched_id, suggested = record._find_match()
            action = record._proposed_action(matched_id)
            record.write(
                {
                    "record_model": model if matched_id else False,
                    "record_id": matched_id,
                    "match_suggested": suggested,
                    "action": action,
                }
            )

    def _find_match(self):
        """The model, id and whether the match is a suggestion; an id of 0 is no match."""
        self.ensure_one()
        values = self._effective_values()
        model = KIND_MODELS[self.kind]
        self.env[model].flush_model()
        table = self.env[model]._table
        if self.kind == KIND_PARAMETER_METHOD:
            return model, self._find_pair(values), False
        code = values.get("code")
        if self.kind in CODE_KINDS or (self.kind == KIND_TESTING_FIELD and code):
            query = SQL(
                r"SELECT id FROM %s WHERE lower(regexp_replace(normalize(code, NFKC), '\s', '', 'g')) = %s "
                "ORDER BY id LIMIT 1",
                SQL.identifier(table),
                normalize_code(code or ""),
            )
            found = self.env.execute_query(query)
            return model, found[0][0] if found else 0, False
        name = values.get("name")
        if not name:
            return model, 0, False
        name_sql = SQL("COALESCE(name->>%s, name->>'en_US')", self.lang)
        query = SQL(
            "SELECT id FROM %(table)s WHERE similarity(%(name)s, %(value)s) >= %(threshold)s "
            "ORDER BY similarity(%(name)s, %(value)s) DESC, id LIMIT 1",
            table=SQL.identifier(table),
            name=name_sql,
            value=name,
            threshold=NAME_MATCH_THRESHOLD,
        )
        found = self.env.execute_query(query)
        return model, found[0][0] if found else 0, bool(found)

    def _find_pair(self, values):
        """The active pair of the matched parameter and method, else 0."""
        needs = {
            kind: self._resolve_need(kind, values.get(key, ""))
            for key, kind in KIND_NEEDS[KIND_PARAMETER_METHOD].items()
        }
        parameter, method = needs[KIND_TEST_PARAMETER], needs[KIND_TESTING_METHOD]
        if not (parameter.record_id and method.record_id):
            return 0
        pair = (
            self.env[MODEL_PARAMETER_METHOD]
            .sudo()
            .search([("parameter_id", "=", parameter.record_id), ("method_id", "=", method.record_id)], limit=1)
        )
        return pair.id

    def _matched_record(self):
        """The Laboratory record it matches, empty when there is none or it was deleted."""
        self.ensure_one()
        model = self.env[KIND_MODELS[self.kind]]
        if not self.record_id:
            return model
        return model.sudo().browse(self.record_id).exists()

    def _proposed_action(self, matched_id) -> str:
        if not matched_id:
            return ACTION_CREATE
        return ACTION_LINK if self._same_values(matched_id) else ACTION_UPDATE

    def _same_values(self, matched_id) -> bool:
        return not self._differences(matched_id)

    def _differences(self, matched_id) -> list:
        """The compared values of the matched record that differ, as (key, current, wanted), the record read in the
        staged language. A way of testing has nothing but its pair, so it never differs, and a value the staged record
        does not give, or gives as a date that is not ISO, is no change."""
        if self.kind == KIND_PARAMETER_METHOD:
            return []
        record = self.env[KIND_MODELS[self.kind]].sudo().browse(matched_id).exists()
        if not record:
            return []
        record = record.with_context(lang=self.lang, active_test=False)
        values = self._effective_values()
        differences = []
        for key in COMPARED_KEYS[self.kind]:
            wanted = values.get(key) or ""
            if not wanted or (record._fields[key].type == "date" and not is_iso_date(wanted)):
                continue
            current = record[key]
            current = (current.isoformat() if hasattr(current, "isoformat") else current) or ""
            if key == "code":
                same = normalize_code(current) == normalize_code(wanted)
            else:
                same = current == wanted
            if not same:
                differences.append((key, current, wanted))
        return differences
