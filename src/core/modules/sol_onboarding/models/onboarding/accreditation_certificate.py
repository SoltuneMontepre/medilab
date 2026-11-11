from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_ACCREDITATION_CERTIFICATE
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_accreditation_certificate as AccreditationCertificateBase
else:
    AccreditationCertificateBase = object


# Giấy Chứng Nhận Công Nhận
class AccreditationCertificate(models.Model, AccreditationCertificateBase):
    _name = MODEL_ACCREDITATION_CERTIFICATE
    _inherit = [MODEL_ACCREDITATION_CERTIFICATE, MODEL_ONBOARDING_ORIGIN_MIXIN]
