from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT,
    MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import (
        Model_medilab_accreditation_certificate_import_line as AccreditationCertificateImportLineBase,
    )
else:
    AccreditationCertificateImportLineBase = object


# Dòng Nhập Phạm Vi
class AccreditationCertificateImportLine(models.TransientModel, AccreditationCertificateImportLineBase):
    _name = MODEL_ACCREDITATION_CERTIFICATE_IMPORT_LINE
    _description = "Accreditation Certificate Import Line"
    _order = "id"

    if not TYPE_CHECKING:
        # The import wizard this row belongs to.
        import_id = fields.Many2one(MODEL_ACCREDITATION_CERTIFICATE_IMPORT, required=True, ondelete="cascade")
        # Standard reference of the method, such as TCVN 6187-1:2009.
        code = fields.Char()
        # Title of the standard in the language of the list; the code when left empty.
        name = fields.Char(string="Title")
        # Parameters the scope line accredits with the method.
        parameter_ids = fields.Many2many(
            MODEL_TEST_PARAMETER,
            "medilab_accreditation_import_line_parameter_rel",
            "line_id",
            "parameter_id",
            string="Parameters",
        )
        # Sample types the scope line accredits with the method.
        sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            "medilab_accreditation_import_line_sample_type_rel",
            "line_id",
            "sample_type_id",
            string="Sample Types",
        )
