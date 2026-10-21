from odoo import models
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_STAGED_RECORD
from odoo.addons.sol_onboarding.constants.onboarding import (
    ACTION_CREATE,
    ACTION_LINK,
    ACTION_UPDATE,
    KIND_CERTIFICATE,
    KIND_MODELS,
    KIND_PARAMETER_METHOD,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_FIELD,
    KIND_TESTING_METHOD,
    STAGED_ACCEPTED,
    STAGED_TO_REVIEW,
)
from odoo.addons.sol_onboarding.services.parsing import clean_text

NAME_MATCH_THRESHOLD = 0.6

# Kinds that match by code, and the kinds that match by name.
CODE_KINDS = (KIND_CERTIFICATE, KIND_TESTING_METHOD)
NAME_KINDS = (KIND_SAMPLE_TYPE, KIND_TEST_PARAMETER)
# Values that decide between linking a record and updating it; a method's testing field does not count.
COMPARED_KEYS = {
    KIND_CERTIFICATE: ("code", "issuing_body", "valid_from", "valid_until"),
    KIND_TESTING_FIELD: ("code", "name"),
    KIND_TESTING_METHOD: ("code", "name"),
    KIND_SAMPLE_TYPE: ("name",),
    KIND_TEST_PARAMETER: ("name",),
}


def normalize_code(value: str) -> str:
    return "".join(clean_text(value).split()).lower()


# Bản Ghi Chờ Duyệt: the Laboratory record a staged record matches and the action it proposes.
class OnboardingStagedRecordMatching(models.Model):
    _inherit = MODEL_ONBOARDING_STAGED_RECORD

    def write(self, vals):
        result = super().write(vals)
        if "edited_values" in vals and "record_model" not in vals and "record_id" not in vals:
            self._match()
        return result

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
            action = ACTION_CREATE
            if matched_id:
                action = ACTION_LINK if record._same_values(model, matched_id) else ACTION_UPDATE
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
                r"SELECT id FROM %s WHERE lower(regexp_replace(code, '\s', '', 'g')) = %s ORDER BY id LIMIT 1",
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
        parameter = self._resolve_need(KIND_TEST_PARAMETER, values.get("parameter_key", ""))
        method = self._resolve_need(KIND_TESTING_METHOD, values.get("method_key", ""))
        if not (parameter.record_id and method.record_id):
            return 0
        pair = (
            self.env[MODEL_PARAMETER_METHOD]
            .sudo()
            .search([("parameter_id", "=", parameter.record_id), ("method_id", "=", method.record_id)], limit=1)
        )
        return pair.id

    def _same_values(self, model, matched_id) -> bool:
        """Whether the compared values equal those of the matched record, read in the staged language. A way of
        testing has nothing but its pair, so it always links."""
        if self.kind == KIND_PARAMETER_METHOD:
            return True
        record = self.env[model].sudo().browse(matched_id).with_context(lang=self.lang, active_test=False)
        values = self._effective_values()
        for key in COMPARED_KEYS[self.kind]:
            current = record[key]
            current = current.isoformat() if hasattr(current, "isoformat") else current
            wanted = values.get(key) or ""
            if key == "code":
                current, wanted = normalize_code(current or ""), normalize_code(wanted)
            if (current or "") != wanted:
                return False
        return True
