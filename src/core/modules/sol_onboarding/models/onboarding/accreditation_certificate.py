from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_ACCREDITATION_CERTIFICATE
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN


# Giấy Chứng Nhận Công Nhận
class AccreditationCertificate(models.Model):
    _name = MODEL_ACCREDITATION_CERTIFICATE
    _inherit = [MODEL_ACCREDITATION_CERTIFICATE, MODEL_ONBOARDING_ORIGIN_MIXIN]
