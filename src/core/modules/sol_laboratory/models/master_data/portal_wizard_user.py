from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_PORTAL_WIZARD_USER

if TYPE_CHECKING:
    from medilab_model_types import Model_portal_wizard_user as PortalWizardUserBase
else:
    PortalWizardUserBase = object


# Người Dùng Cổng Thông Tin: those who maintain customers invite them without Odoo's contact rights.
class PortalWizardUser(models.TransientModel, PortalWizardUserBase):
    _inherit = MODEL_PORTAL_WIZARD_USER

    def _send_email(self):
        # The invitation's sign-up link needs the right to write the invited contact, which only Odoo's contact
        # managers hold. The wizard itself is open only to them and to those who maintain customers.
        return super(PortalWizardUser, self.sudo())._send_email()
