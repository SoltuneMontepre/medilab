from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_UI_VIEW
from odoo.addons.sol_laboratory.constants.views import TIMELINE_VIEW

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_ui_view as IrUiViewBase
else:
    IrUiViewBase = object


# Giao Diện
class IrUiView(models.Model, IrUiViewBase):
    _inherit = MODEL_IR_UI_VIEW

    if not TYPE_CHECKING:
        # Kind of view; adds the timeline of records with a start and an end.
        type = fields.Selection(selection_add=[(TIMELINE_VIEW, "Timeline")], ondelete={TIMELINE_VIEW: "cascade"})

    def _get_view_info(self):
        return {**super()._get_view_info(), TIMELINE_VIEW: {"icon": "view_timeline"}}
