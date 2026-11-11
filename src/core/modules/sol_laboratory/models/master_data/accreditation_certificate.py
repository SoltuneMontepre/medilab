from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE_TEST,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_accreditation_certificate as AccreditationCertificateBase
else:
    AccreditationCertificateBase = object

# Fields that change what a certificate accredits, besides its scope lines.
VALIDITY_FIELDS = {"valid_from", "valid_until", "active"}


# Giấy Chứng Nhận Công Nhận
class AccreditationCertificate(models.Model, AccreditationCertificateBase):
    _name = MODEL_ACCREDITATION_CERTIFICATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Accreditation Certificate"
    _order = "code"
    _rec_name = "code"
    _rec_names_search = ("code", "issuing_body")
    _permission_actions = ("create", "edit", "archive", "delete")
    _audit_children = ("scope_line_ids",)

    if not TYPE_CHECKING:
        # Certificate number, such as VILAS 123.
        code = fields.Char(required=True, copy=False, index="trigram")
        # The body that issued the certificate.
        issuing_body = fields.Char()
        # First day the certificate is valid; empty means valid from any date.
        valid_from = fields.Date()
        # Last day the certificate is valid; empty means valid until any date.
        valid_until = fields.Date()
        # Lines of the scope, each with a testing method, its parameters and its sample types.
        scope_line_ids = fields.One2many(MODEL_ACCREDITATION_SCOPE_LINE, "certificate_id", string="Scope")
        # Testing methods the scope lines name.
        method_ids = fields.Many2many(
            MODEL_TESTING_METHOD,
            compute="_compute_method_ids",
            search="_search_method_ids",
            string="Testing Methods",
        )
        # False when the certificate is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The number of an accreditation certificate must be unique.")

    @api.depends("scope_line_ids.method_id")
    def _compute_method_ids(self):
        for certificate in self:
            certificate.method_ids = certificate.scope_line_ids.method_id

    def _search_method_ids(self, operator, value):
        return Domain("scope_line_ids.method_id", operator, value)

    @api.constrains("valid_from", "valid_until")
    def _check_validity_dates(self):
        for certificate in self:
            if certificate.valid_from and certificate.valid_until and certificate.valid_from > certificate.valid_until:
                raise ValidationError(
                    self.env._(
                        "The first valid day of certificate %s cannot be after its last valid day.",
                        certificate.code,
                    )
                )

    @api.model
    def _laboratory_today(self):
        return datetime.now(ZoneInfo(self.env.company.tz or "UTC")).date()

    @api.model
    def _recompute_accreditation(self, methods):
        """Work out again whether the ways of testing that use the methods are accredited on their sample types, and
        their sample tests still open."""
        methods = methods.exists()
        if not methods:
            return
        applicabilities = (
            self.env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE]
            .sudo()
            .with_context(active_test=False)
            .search([("parameter_method_id.method_id", "in", methods.ids)])
        )
        applicabilities._recompute_is_accredited()
        self.env[MODEL_SAMPLE_TEST]._refresh_accreditation_of_methods(methods)

    def write(self, vals):
        result = super().write(vals)
        if VALIDITY_FIELDS & set(vals):
            self._recompute_accreditation(self.scope_line_ids.method_id)
        return result

    def unlink(self):
        methods = self.scope_line_ids.method_id
        result = super().unlink()
        self._recompute_accreditation(methods)
        return result

    def action_import_scope(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import Scope Lines"),
            "res_model": MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_certificate_id": self.id,
                "default_lang": self.env.lang,
            },
        }
