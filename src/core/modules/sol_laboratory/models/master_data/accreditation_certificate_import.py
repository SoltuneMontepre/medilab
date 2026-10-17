from psycopg2 import errorcodes
from psycopg2.errors import IntegrityError, UniqueViolation

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, ValidationError
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)


# Nhập Phương Pháp Từ Giấy Chứng Nhận
class AccreditationCertificateImport(models.TransientModel):
    _name = MODEL_ACCREDITATION_CERTIFICATE_IMPORT
    _description = "Import Methods from an Accreditation Certificate"

    # The certificate that receives the imported methods.
    certificate_id = fields.Many2one(MODEL_ACCREDITATION_CERTIFICATE, required=True, ondelete="cascade")
    # Testing field assigned to every newly created method in the list.
    field_id = fields.Many2one(MODEL_TESTING_FIELD, required=True, string="Testing Field")
    # Language of the titles in the list.
    lang = fields.Selection(selection="_lang_selection", required=True)
    # Rows of standard code and title to import.
    line_ids = fields.One2many(
        MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE,
        "import_id",
        string="Methods",
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
        lines = self.line_ids
        if not lines:
            raise ValidationError(self.env._("Enter at least one method to import."))

        parsed = []
        seen = set()
        for index, line in enumerate(lines, start=1):
            code = (line.code or "").strip()
            title = (line.name or "").strip()
            if not code or not title:
                raise ValidationError(
                    self.env._(
                        "Row %(row)s has no code or title. Nothing was imported.",
                        row=index,
                    )
                )
            if code in seen:
                raise ValidationError(
                    self.env._(
                        "The code %(code)s appears more than once in the list. Nothing was imported.",
                        code=code,
                    )
                )
            seen.add(code)
            parsed.append((code, title))

        methods = self.env[MODEL_TESTING_METHOD]
        existing = methods.with_context(active_test=False).search([("code", "in", [code for code, _ in parsed])])
        by_code = {method.code: method for method in existing}
        missing = [code for code, _ in parsed if code not in by_code]
        if missing:
            methods.check_access("create")

        # Outer savepoint: any failure after creates start rolls back methods and scope links.
        with self.env.cr.savepoint():
            method_ids = []
            for code, title in parsed:
                method = by_code.get(code)
                if method is None:
                    method = self._create_method(code, title)
                    by_code[code] = method
                method_ids.append(method.id)

            certificate.write({"method_ids": [Command.link(method_id) for method_id in method_ids]})
        return {"type": "ir.actions.act_window_close"}

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
            if not isinstance(error, UniqueViolation) and error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Same-transaction races are visible in this snapshot.
            self.env.cr.execute(
                "SELECT id FROM medilab_testing_method WHERE code = %s",
                [code],
            )
            row = self.env.cr.fetchone()
            if row:
                return methods.browse(row[0])
            # Concurrent commit under REPEATABLE READ is invisible here (and cannot be linked).
            # ConcurrencyError is what odoo.http.retrying retries without needing a SQLSTATE.
            raise ConcurrencyError(
                self.env._(
                    "Another transaction created testing method %s; the import will retry.",
                    code,
                )
            ) from error


# Dòng Nhập Phương Pháp
class AccreditationCertificateImportLine(models.TransientModel):
    _name = MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE
    _description = "Accreditation Certificate Import Line"
    _order = "id"

    # The import wizard this row belongs to.
    import_id = fields.Many2one(MODEL_ACCREDITATION_CERTIFICATE_IMPORT, required=True, ondelete="cascade")
    # Standard reference of the method, such as TCVN 6187-1:2009.
    code = fields.Char()
    # Title of the standard in the language of the list.
    name = fields.Char(string="Title")
