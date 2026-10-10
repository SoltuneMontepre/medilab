from odoo import fields, models

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_SAMPLE_TYPE,
)


# Quy Chuẩn
class Regulation(models.Model):
    _name = MODEL_REGULATION
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Regulation"
    _rec_name = "code"
    _order = "code"
    _rec_names_search = ["code", "name"]

    # Unique reference of the regulation, such as QCVN 6-1:2010/BYT.
    code = fields.Char(required=True, copy=False)
    # Title of the regulation in each language.
    name = fields.Char(required=True, translate=True)
    # The ministry or body that issued the regulation.
    issuing_authority = fields.Char()
    # Sample types the regulation applies to.
    sample_type_ids = fields.Many2many(
        MODEL_SAMPLE_TYPE,
        "medilab_regulation_sample_type_rel",
        "regulation_id",
        "sample_type_id",
        ondelete="restrict",
        string="Sample Types",
    )
    # Limits the regulation sets, one per parameter.
    limit_ids = fields.One2many(MODEL_REGULATION_LIMIT, "regulation_id", string="Limits")
    # False when the regulation is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The reference of a regulation must be unique.")
