from odoo import fields, models

from odoo.addons.laboratory.constants.views import TIMELINE_VIEW


# Links window actions to the views they open, including the timeline.
class IrActionsActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    # Kind of view the action opens.
    view_mode = fields.Selection(selection_add=[(TIMELINE_VIEW, "Timeline")], ondelete={TIMELINE_VIEW: "cascade"})
