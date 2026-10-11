from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PARAMETER_METHOD,
    MODEL_QUALITY_REGISTRATION,
)


# Hồ Sơ Đăng Ký Chất Lượng
class QualityRegistration(models.Model):
    _name = MODEL_QUALITY_REGISTRATION
    _inherit = [MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _description = "Quality Registration"
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the dossier; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # Dossier name in each language.
    name = fields.Char(required=True, translate=True)
    # The ministry or body the dossier is registered with.
    issuing_authority = fields.Char()
    # First day the registration is valid.
    valid_from = fields.Date()
    # Last day the registration is valid; it counts as expired after this date.
    valid_until = fields.Date(index=True)
    # Mark printed after the name of each covered parameter on the report, such as (*).
    report_mark = fields.Char()
    # Parameter and method pairs the dossier covers.
    parameter_method_ids = fields.Many2many(
        MODEL_PARAMETER_METHOD,
        "medilab_quality_registration_parameter_method_rel",
        "registration_id",
        "parameter_method_id",
        string="Covered Ways of Testing",
    )
    # False when the dossier is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a quality registration must be unique.")
