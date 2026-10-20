from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_ACT_WINDOW_VIEW
from odoo.addons.sol_laboratory.constants.views import TIMELINE_VIEW


# Links window actions to the views they open, including the timeline.
class IrActionsActWindowView(models.Model):
    _inherit = MODEL_IR_ACTIONS_ACT_WINDOW_VIEW

    # Kind of view the action opens.
    view_mode = fields.Selection(selection_add=[(TIMELINE_VIEW, "Timeline")], ondelete={TIMELINE_VIEW: "cascade"})
