from odoo import fields, models

from odoo.addons.sol_laboratory.constants.views import TIMELINE_VIEW


# Giao Diện
class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    # Kind of view; adds the timeline of records with a start and an end.
    type = fields.Selection(selection_add=[(TIMELINE_VIEW, "Timeline")], ondelete={TIMELINE_VIEW: "cascade"})

    def _get_view_info(self):
        return {**super()._get_view_info(), TIMELINE_VIEW: {"icon": "view_timeline"}}
