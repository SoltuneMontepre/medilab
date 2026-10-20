from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
    MODEL_RES_USERS_APIKEYS,
)


# Máy Tính Đồng Bộ
class LaboratoryDevice(models.Model):
    _name = MODEL_LABORATORY_DEVICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Device"
    _order = "last_seen_at desc, id desc"
    # Signing in creates a device and revoking it is editing it; it is never deleted, as its versions name it.
    _permission_actions = ("read", "edit")
    # Every call of the device moves it.
    _audit_exclude = ("last_seen_at",)

    # The user the device signs in as.
    user_id = fields.Many2one(MODEL_RES_USERS, string="User", required=True, ondelete="cascade", readonly=True)
    # Id the application generates once per installation.
    client_uid = fields.Char(string="Installation ID", required=True, readonly=True)
    # Name of the computer.
    name = fields.Char(required=True)
    # linux or windows.
    platform = fields.Selection([("linux", "Linux"), ("windows", "Windows")], required=True, readonly=True)
    # The Odoo API key of the device; the key itself is never stored here.
    api_key_id = fields.Many2one(MODEL_RES_USERS_APIKEYS, string="API Key", readonly=True, copy=False)
    # When the device last called the API.
    last_seen_at = fields.Datetime(string="Last Seen", readonly=True)
    # When the device was revoked; empty while it can sign in.
    revoked_at = fields.Datetime(string="Revoked At", readonly=True, copy=False)

    _user_client_unique = models.Constraint(
        "UNIQUE(user_id, client_uid)", "This installation is already signed in for this person."
    )
