import logging
from typing import TYPE_CHECKING

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.audit import MASK_SECRET
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LOCK_MIXIN,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_mobile_device as MobileDeviceBase
else:
    MobileDeviceBase = object

_logger = logging.getLogger(__name__)


# Thiết Bị Di Động
class MobileDevice(models.Model, MobileDeviceBase):
    _name = MODEL_MOBILE_DEVICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Mobile Device"
    _permission_actions = ("read", "create", "edit", "archive", "delete")
    # The app refreshes it each time it starts.
    _audit_exclude = ("last_seen_at",)

    if not TYPE_CHECKING:
        # The signed-in phone the token belongs to.
        laboratory_device_id = fields.Many2one(
            MODEL_LABORATORY_DEVICE, string="Phone", required=True, ondelete="cascade", readonly=True
        )
        # The Odoo user signed in on the phone.
        user_id = fields.Many2one(related="laboratory_device_id.user_id", store=True, index=True)
        # Registration token Firebase Cloud Messaging gives the app.
        token = fields.Char(required=True, copy=False, audit_mask=MASK_SECRET)
        # android or ios, the phone's platform.
        platform = fields.Selection(related="laboratory_device_id.platform", store=True)
        # When the app last registered the token.
        last_seen_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # False once the phone is no longer signed in or Firebase rejected the token.
        active = fields.Boolean(default=True)

    _token_unique = models.Constraint("UNIQUE(token)", "This device token is already registered.")
    _phone_unique = models.Constraint("UNIQUE(laboratory_device_id)", "This phone already has a push token.")

    @api.model
    def _register_token(self, phone, token):
        """Register the token Firebase gave the app for the signed-in phone, or replace its old one, and turn it on. A
        token registered for another phone, such as after the app is reinstalled, moves to this one, so a token is never
        pushed to two phones."""
        tokens = self.sudo().with_context(active_test=False)
        tokens.search([("token", "=", token), ("laboratory_device_id", "!=", phone.id)]).unlink()
        values = {"token": token, "last_seen_at": fields.Datetime.now(), "active": True}
        current = tokens.search([("laboratory_device_id", "=", phone.id)])
        if current:
            current.write(values)
            return current
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return tokens.create({"laboratory_device_id": phone.id, **values})
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Two registrations at once; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Another registration of this push token happened meanwhile; it is run again.")
            ) from error

    @api.model
    def _cleanup_domain(self, cutoff):
        """The tokens the cleanup job removes: turned off before the cutoff."""
        return [("active", "=", False), ("write_date", "<", cutoff)]

    def turn_off(self, reason):
        """Firebase reported a permanent token failure."""
        _logger.info("Mobile device turned off: %s", reason)
        self.sudo().write({"active": False})
