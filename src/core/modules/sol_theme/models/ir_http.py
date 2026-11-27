from typing import TYPE_CHECKING

from odoo import models

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_http as IrHttpBase
else:
    IrHttpBase = object


# Định Tuyến HTTP: the portal reads this module's translations of Odoo's own screen strings, as the back office does.
class IrHttp(models.AbstractModel, IrHttpBase):
    _inherit = "ir.http"

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        return [*super()._get_translation_frontend_modules_name(), "sol_theme"]
