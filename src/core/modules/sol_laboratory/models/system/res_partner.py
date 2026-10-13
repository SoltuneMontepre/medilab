from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_RES_PARTNER


# Liên Hệ
class ResPartner(models.Model):
    _name = MODEL_RES_PARTNER
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_RES_PARTNER]
    # When the person last dismissed their calendar alarms.
    _audit_exclude = ("calendar_last_notif_ack",)

    # Contact name, searched with the subcontractor.
    name = fields.Char(index="trigram")
