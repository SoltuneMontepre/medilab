from odoo import fields, models


# Liên Hệ
class ResPartner(models.Model):
    _inherit = "res.partner"

    # Contact name, searched with the subcontractor.
    name = fields.Char(index="trigram")
