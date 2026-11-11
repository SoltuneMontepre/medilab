from typing import TYPE_CHECKING

from psycopg2 import errorcodes
from psycopg2.errors import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, ValidationError
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_accreditation_certificate_import as AccreditationCertificateImportBase
else:
    AccreditationCertificateImportBase = object


# Nhập Phạm Vi Từ Giấy Chứng Nhận
class AccreditationCertificateImport(models.TransientModel, AccreditationCertificateImportBase):
    _name = MODEL_ACCREDITATION_CERTIFICATE_IMPORT
    _description = "Import Scope Lines into an Accreditation Certificate"

    if not TYPE_CHECKING:
        # The certificate that receives the imported scope lines.
        certificate_id = fields.Many2one(
            MODEL_ACCREDITATION_CERTIFICATE,
            required=True,
            ondelete="cascade",
            string="Accreditation Certificate",
        )
        # Testing field assigned to every method the import creates.
        field_id = fields.Many2one(MODEL_TESTING_FIELD, required=True, string="Testing Field")
        # Language of the titles in the list.
        lang = fields.Selection(selection="_lang_selection", required=True)
        # Rows to import, each a scope line with its standard code, title, parameters and sample types.
        line_ids = fields.One2many(
            MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE,
            "import_id",
            string="Scope Lines",
        )

    @api.model
    def _lang_selection(self):
        return self.env["res.lang"].get_installed()

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "lang" in fields_list and not defaults.get("lang"):
            defaults["lang"] = self.env.lang
        return defaults

    def action_import(self):
        self.ensure_one()
        certificate = self.certificate_id
        certificate._check_permission("edit")
        titles, rows = self._read_rows()

        methods = self.env[MODEL_TESTING_METHOD]
        existing = methods.with_context(active_test=False).search([("code", "in", list(titles))])
        by_code = {method.code: method for method in existing}
        if any(code not in by_code for code in titles):
            methods.check_access("create")
        self.env[MODEL_ACCREDITATION_SCOPE_LINE].check_access("create")

        # Outer savepoint: any failure after creates start rolls back methods and scope lines.
        with self.env.cr.savepoint():
            for code, title in titles.items():
                if code not in by_code:
                    by_code[code] = self._create_method(code, title or code)
            commands = self._new_line_commands(certificate, by_code, rows)
            if commands:
                certificate.write({"scope_line_ids": commands})
        return {"type": "ir.actions.act_window_close"}

    def _read_rows(self):
        """Return the title of each code and the rows as (code, parameters, sample types); refuse the whole import
        on an empty list or a row without a code, a parameter or a sample type."""
        if not self.line_ids:
            raise ValidationError(self.env._("Enter at least one scope line to import."))
        titles = {}
        rows = []
        for index, line in enumerate(self.line_ids, start=1):
            code = (line.code or "").strip()
            if not code:
                raise ValidationError(self.env._("Row %(row)s has no code. Nothing was imported.", row=index))
            if not line.parameter_ids or not line.sample_type_ids:
                raise ValidationError(
                    self.env._(
                        "Row %(row)s needs at least one parameter and one sample type. Nothing was imported.",
                        row=index,
                    )
                )
            # A code listed on several rows takes the first title given; without any it takes its code.
            if not titles.get(code):
                titles[code] = (line.name or "").strip()
            rows.append((code, line.parameter_ids, line.sample_type_ids))
        return titles, rows

    @api.model
    def _new_line_commands(self, certificate, by_code, rows):
        """Commands creating a scope line for each row the certificate and the earlier rows do not already have."""
        scope = {
            (line.method_id.id, frozenset(line.parameter_ids.ids), frozenset(line.sample_type_ids.ids))
            for line in certificate.scope_line_ids
        }
        commands = []
        for code, parameters, sample_types in rows:
            key = (by_code[code].id, frozenset(parameters.ids), frozenset(sample_types.ids))
            if key in scope:
                continue
            scope.add(key)
            commands.append(
                Command.create(
                    {
                        "method_id": key[0],
                        "parameter_ids": [Command.set(persisted_ids(parameters))],
                        "sample_type_ids": [Command.set(persisted_ids(sample_types))],
                    }
                )
            )
        return commands

    def _create_method(self, code, title):
        methods = self.env[MODEL_TESTING_METHOD].with_context(lang=self.lang)
        try:
            with self.env.cr.savepoint():
                return methods.create(
                    {
                        "code": code,
                        "name": title,
                        "field_id": self.field_id.id,
                    }
                )
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            existing = methods.with_context(active_test=False).search([("code", "=", code)], limit=1)
            if existing:
                return existing
            # Concurrent commit under REPEATABLE READ is invisible here (and cannot be linked).
            # ConcurrencyError is what odoo.http.retrying retries without needing a SQLSTATE.
            raise ConcurrencyError(
                self.env._(
                    "Another transaction created testing method %s; the import will retry.",
                    code,
                )
            ) from error
