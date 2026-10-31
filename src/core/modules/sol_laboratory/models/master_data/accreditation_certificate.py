from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_accreditation_certificate as AccreditationCertificateBase
else:
    AccreditationCertificateBase = object


# Giấy Chứng Nhận Công Nhận
class AccreditationCertificate(models.Model, AccreditationCertificateBase):
    _name = MODEL_ACCREDITATION_CERTIFICATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Accreditation Certificate"
    _order = "code"
    _rec_name = "code"
    _rec_names_search = ("code", "issuing_body")
    _permission_actions = ("create", "edit", "archive", "delete")

    if not TYPE_CHECKING:
        # Certificate number, such as VILAS 123.
        code = fields.Char(required=True, copy=False, index="trigram")
        # The body that issued the certificate.
        issuing_body = fields.Char()
        # First day the certificate is valid; empty means valid from any date.
        valid_from = fields.Date()
        # Last day the certificate is valid; empty means valid until any date.
        valid_until = fields.Date()
        # Testing methods in the scope of the certificate.
        method_ids = fields.Many2many(
            MODEL_TESTING_METHOD,
            "medilab_accreditation_certificate_method_rel",
            "certificate_id",
            "method_id",
            ondelete="restrict",
            string="Testing Methods",
        )
        # False when the certificate is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The number of an accreditation certificate must be unique.")

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
    def _accredited_methods(self, methods, today=None):
        """Return the subset of methods covered by an active certificate valid on today."""
        methods = methods.exists()
        if not methods:
            return methods
        today = today or self._laboratory_today()
        return (
            self.with_context(active_test=True)
            .search(
                [
                    ("method_ids", "in", methods.ids),
                    "|",
                    ("valid_from", "=", False),
                    ("valid_from", "<=", today),
                    "|",
                    ("valid_until", "=", False),
                    ("valid_until", ">=", today),
                ]
            )
            .mapped("method_ids")
            & methods
        )

    def _recompute_linked_pairs(self, methods=None):
        methods = methods if methods is not None else self.mapped("method_ids")
        self.env[MODEL_PARAMETER_METHOD]._recompute_for_methods(methods)

    @api.model_create_multi
    def create(self, vals_list):
        certificates = super().create(vals_list)
        certificates.flush_recordset()
        certificates._recompute_linked_pairs(certificates.mapped("method_ids"))
        return certificates

    def write(self, vals):
        scope_keys = {"method_ids", "valid_from", "valid_until", "active"}
        methods_before = self.mapped("method_ids") if scope_keys & set(vals) else self.env[MODEL_TESTING_METHOD]
        result = super().write(vals)
        if scope_keys & set(vals):
            method_ids = set(methods_before.ids) | set(self.mapped("method_ids").ids)
            self._recompute_linked_pairs(self.env[MODEL_TESTING_METHOD].browse(method_ids))
        return result

    def unlink(self):
        methods = self.mapped("method_ids")
        result = super().unlink()
        self.env[MODEL_PARAMETER_METHOD]._recompute_for_methods(methods)
        return result

    def action_import_methods(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import Methods"),
            "res_model": MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_certificate_id": self.id,
                "default_lang": self.env.lang,
            },
        }
