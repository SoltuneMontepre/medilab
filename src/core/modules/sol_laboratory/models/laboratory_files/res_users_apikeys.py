from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_RES_USERS_APIKEYS

if TYPE_CHECKING:
    from medilab_model_types import Model_res_users_apikeys as ResUsersApikeysBase
else:
    ResUsersApikeysBase = object


# Khóa API: removing the key of a signed-in computer signs the computer out, wherever the key is removed from.
class ResUsersApikeys(models.Model, ResUsersApikeysBase):
    _inherit = MODEL_RES_USERS_APIKEYS

    def unlink(self):
        # Before the rows go, so the audit trail names the key the computer had. Odoo makes no foreign key to its keys,
        # and every removal of a key, from the person's preferences too, comes here; only its cleanup of expired keys
        # deletes rows with SQL, and computers' keys never expire.
        devices = self.env[MODEL_LABORATORY_DEVICE].sudo().search([("api_key_id", "in", self.ids)])
        devices.write({"api_key_id": False})
        return super().unlink()
