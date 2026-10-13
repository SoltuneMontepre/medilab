from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CHEMICAL,
    MODEL_PERMISSION_MIXIN,
    MODEL_TESTING_METHOD,
)


# Hóa Chất
class Chemical(models.Model):
    _name = MODEL_CHEMICAL
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Chemical"
    _order = "code"
    _rec_names_search = ("name", "code", "cas_number")
    _permission_actions = ("create", "edit", "archive", "delete")

    # Unique code of the chemical.
    code = fields.Char(required=True, copy=False, index="trigram")
    # Chemical name in each language.
    name = fields.Char(required=True, translate=True, index="trigram")
    # CAS registry number, such as 7647-14-5.
    cas_number = fields.Char(string="CAS Number", index="trigram")
    # Chemical formula, such as NaCl.
    formula = fields.Char()
    # Grade or purity, such as "AR, ≥ 99.5 %".
    grade = fields.Char()
    # How the chemical must be stored, in each language.
    storage_conditions = fields.Text(translate=True)
    # Testing methods that use the chemical.
    method_ids = fields.Many2many(
        MODEL_TESTING_METHOD,
        "medilab_chemical_method_rel",
        "chemical_id",
        "method_id",
        ondelete="restrict",
        string="Testing Methods",
    )
    # False when the chemical is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a chemical must be unique.")
