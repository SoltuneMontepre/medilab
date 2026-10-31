from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CHEMICAL,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_method as TestingMethodBase
else:
    TestingMethodBase = object


# Phương Pháp Thử
class TestingMethod(models.Model, TestingMethodBase):
    _name = MODEL_TESTING_METHOD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Testing Method"
    _rec_name = "code"
    _order = "code"
    _rec_names_search = ("code", "name")
    _permission_actions = ("create", "edit", "archive", "delete")
    _audit_children = ("step_ids",)

    if not TYPE_CHECKING:
        # Unique standard reference of the method, such as TCVN 6187-1:2009.
        code = fields.Char(required=True, copy=False, index="trigram")
        # Title of the standard in each language, such as "Water quality — Detection of coliforms".
        name = fields.Char(required=True, translate=True, index="trigram")
        # The testing field the method belongs to.
        field_id = fields.Many2one(
            MODEL_TESTING_FIELD, required=True, ondelete="restrict", index=True, string="Testing Field"
        )
        # Chemicals the method uses.
        chemical_ids = fields.Many2many(
            MODEL_CHEMICAL,
            "medilab_chemical_method_rel",
            "method_id",
            "chemical_id",
            ondelete="restrict",
            string="Chemicals",
        )
        # Accreditation certificates that list this method, archived ones included; linked from the certificate only.
        certificate_ids = fields.Many2many(
            MODEL_ACCREDITATION_CERTIFICATE,
            "medilab_accreditation_certificate_method_rel",
            "method_id",
            "certificate_id",
            copy=False,
            context={"active_test": False},
            string="Accreditation Certificates",
        )
        # Steps of the procedure, in step number order.
        step_ids = fields.One2many(MODEL_TESTING_METHOD_STEP, "method_id", string="Steps")
        # False when the method is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a testing method must be unique.")

    def _refuse_certificate_ids(self, vals):
        if "certificate_ids" in vals:
            raise UserError(self.env._("Link testing methods to accreditation certificates from the certificate."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._refuse_certificate_ids(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._refuse_certificate_ids(vals)
        return super().write(vals)
