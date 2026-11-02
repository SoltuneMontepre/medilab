import logging
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

from odoo.addons.sol_laboratory.constants.audit import MASK_SECRET
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_mobile_device as MobileDeviceBase
else:
    MobileDeviceBase = object

PLATFORMS = {"android", "ios"}


# Thiết Bị Di Động
class MobileDevice(models.Model, MobileDeviceBase):
    _name = MODEL_MOBILE_DEVICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Mobile Device"
    _permission_actions = ("read", "create", "edit", "archive", "delete")
    # The app refreshes it each time it starts.
    _audit_exclude = ("last_seen_at",)

    if not TYPE_CHECKING:
        # The Odoo user signed in on the device.
        user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
        # Registration token Firebase Cloud Messaging gives the app.
        token = fields.Char(required=True, copy=False, audit_mask=MASK_SECRET)
        # android or ios.
        platform = fields.Selection([("android", "Android"), ("ios", "iOS")], required=True)
        # When the app last refreshed the token.
        last_seen_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # False when the user signed out or Firebase rejected the token.
        active = fields.Boolean(default=True)

    _token_unique = models.Constraint("UNIQUE(token)", "This device token is already registered.")

    @api.model
    def register_token(self, token, platform):
        """The signed-in user registers the device they are using."""
        if platform not in PLATFORMS or not token:
            raise UserError(self.env._("A mobile device needs a token and a platform."))
        device = self.sudo().search([("token", "=", token)], limit=1)
        values = {
            "user_id": self.env.user.id,
            "platform": platform,
            "last_seen_at": fields.Datetime.now(),
            "active": True,
        }
        if device:
            device.sudo().write(values)
            return device
        return self.sudo().create({"token": token, **values})

    @api.model
    def unregister_token(self, token):
        """Signing out turns this user's token off."""
        device = self.sudo().search([("token", "=", token), ("user_id", "=", self.env.user.id)], limit=1)
        if not device:
            raise AccessError(self.env._("This device is not registered for you."))
        device.sudo().write({"active": False})
        return device

    @api.model
    def _cleanup_domain(self, cutoff):
        """The devices the cleanup job removes: turned off before the cutoff."""
        return [("active", "=", False), ("write_date", "<", cutoff)]

    def turn_off(self, reason):
        """Firebase reported a permanent token failure."""
        _logger.info("Mobile device turned off: %s", reason)
        self.sudo().write({"active": False})
