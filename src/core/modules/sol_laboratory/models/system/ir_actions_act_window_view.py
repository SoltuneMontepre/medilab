from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_ACT_WINDOW_VIEW
from odoo.addons.sol_laboratory.constants.views import TIMELINE_VIEW

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_actions_act_window_view as IrActionsActWindowViewBase
else:
    IrActionsActWindowViewBase = object


# Links window actions to the views they open, including the timeline.
class IrActionsActWindowView(models.Model, IrActionsActWindowViewBase):
    _inherit = MODEL_IR_ACTIONS_ACT_WINDOW_VIEW

    if not TYPE_CHECKING:
        # Kind of view the action opens.
        view_mode = fields.Selection(selection_add=[(TIMELINE_VIEW, "Timeline")], ondelete={TIMELINE_VIEW: "cascade"})
