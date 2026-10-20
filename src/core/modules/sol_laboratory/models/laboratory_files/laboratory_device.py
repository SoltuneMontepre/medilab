from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError
from odoo.tools import SQL

from odoo.addons.base.models.res_users import INDEX_SIZE, KEY_CRYPT_CONTEXT
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_KEY_SCOPE,
    DEVICE_REVOKED,
    INVALID_CREDENTIALS,
    INVALID_KEY,
    INVALID_REQUEST,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
    MODEL_RES_USERS_APIKEYS,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.laboratory_paths import is_name

PLATFORMS = [("linux", "Linux"), ("windows", "Windows")]
# A computer's last call is written at most once a minute, so its parallel calls do not fight over its row.
SEEN_INTERVAL = timedelta(minutes=1)


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
    platform = fields.Selection(PLATFORMS, required=True, readonly=True)
    # The Odoo API key of the device; the key itself is never stored here.
    api_key_id = fields.Many2one(MODEL_RES_USERS_APIKEYS, string="API Key", readonly=True, copy=False)
    # When the device last called the API.
    last_seen_at = fields.Datetime(string="Last Seen", readonly=True)
    # When the device was revoked; empty while it can sign in.
    revoked_at = fields.Datetime(string="Revoked At", readonly=True, copy=False)
    # signed_in while its key exists, signed_out once it is gone, revoked for good once revoked.
    status = fields.Selection(
        [("signed_in", "Signed In"), ("signed_out", "Signed Out"), ("revoked", "Revoked")], compute="_compute_status"
    )

    _user_client_unique = models.Constraint(
        "UNIQUE(user_id, client_uid)", "This installation is already signed in for this person."
    )

    @api.depends("api_key_id", "revoked_at")
    def _compute_status(self):
        for device in self:
            if device.revoked_at:
                device.status = "revoked"
            elif device.sudo().api_key_id:
                device.status = "signed_in"
            else:
                device.status = "signed_out"

    @api.constrains("client_uid", "name")
    def _check_names(self):
        for device in self:
            if not (is_name(device.client_uid) and is_name(device.name)):
                raise ValidationError(
                    self.env._("A computer signs in with its installation id and its name, never a path.")
                )

    @api.model
    def _sign_in(self, login, password, client_uid, name, platform):
        """Sign a computer in with the person's MediLab login. Odoo checks the login as it does for its external API,
        so a person with two-factor authentication uses one of their API keys in place of the password, which is
        never kept. The computer gets a new key, returned only here; signing in again replaces it."""
        if not (is_name(client_uid) and is_name(name) and platform in dict(PLATFORMS)):
            raise LaboratoryFileError(
                INVALID_REQUEST, self.env._("A computer signs in with its installation id, its name and its platform.")
            )
        credential = {"type": "password", "login": login, "password": password}
        try:
            uid = self.env[MODEL_RES_USERS].authenticate(credential, {"interactive": False})["uid"]
        except AccessDenied as error:
            raise LaboratoryFileError(INVALID_CREDENTIALS, self.env._("The login or the password is wrong.")) from error
        devices = self.with_user(uid)
        self.env[MODEL_LABORATORY_FOLDER].with_user(uid)._check_laboratory_files_permission()
        device = devices.sudo().search([("user_id", "=", uid), ("client_uid", "=", client_uid)])
        if device.revoked_at:
            raise LaboratoryFileError(
                DEVICE_REVOKED,
                self.env._("This computer was revoked. Install Medilab Sync again to sign it in as a new computer."),
            )
        # One write per sign-in, so each is one entry of the audit trail. The old key goes after the write, which records
        # it by its name.
        key, key_id = devices._new_key(name)
        if device:
            old_keys = device.api_key_id
            device.write({"name": name, "api_key_id": key_id})
            old_keys._remove()
        else:
            device = devices.sudo().create(
                {"user_id": uid, "client_uid": client_uid, "name": name, "platform": platform, "api_key_id": key_id}
            )
        return device.with_user(uid), key

    def _sign_out(self):
        """The computer signs out: its key is removed, which empties the computer's key, and it can sign in again."""
        self.sudo().api_key_id._remove()

    def action_revoke(self):
        """Revoke the computers for good: their keys stop at once, and their people keep their folders and other
        computers. A person revokes their own computers; revoking someone else's needs the edit permission."""
        self.filtered(lambda device: device.user_id != self.env.user)._check_permission("edit")
        devices = self.filtered(lambda device: not device.revoked_at).sudo()
        keys = devices.api_key_id
        # One write, so revoking is one entry of the audit trail; the keys go after it, which records them by name.
        devices.write({"api_key_id": False, "revoked_at": fields.Datetime.now()})
        keys._remove()

    @api.model
    def _from_key(self, key):
        """The computer of the key Odoo has just verified for the user. Odoo checked the key's hash, a deliberately slow
        one, so the key's row is found by the user, the scope and the key's index, with the expiry Odoo applies; only
        keys that share an index are told apart by their hash. Raw SQL, because the index is not an ORM field."""
        self.env.cr.execute(
            SQL(
                """
                SELECT id, key
                  FROM res_users_apikeys
                 WHERE user_id = %s
                   AND scope = %s
                   AND index = %s
                   AND (expiration_date IS NULL OR expiration_date >= now() at time zone 'utc')
                """,
                self.env.uid,
                DEVICE_KEY_SCOPE,
                key[:INDEX_SIZE],
            )
        )
        rows = self.env.cr.fetchall()
        if len(rows) > 1:
            rows = [(key_id, hashed) for key_id, hashed in rows if KEY_CRYPT_CONTEXT.verify(key, hashed)]
        key_ids = [key_id for key_id, _hashed in rows]
        device = self.sudo().search([("api_key_id", "in", key_ids), ("revoked_at", "=", False)])
        if not device:
            raise LaboratoryFileError(INVALID_KEY, self.env._("This computer is not signed in."))
        device._seen()
        return device.with_env(self.env)

    @api.model
    def _new_key(self, name):
        """A new Odoo API key of the user for a computer, and the id of its row. Odoo keeps only its hash."""
        keys = self.env[MODEL_RES_USERS_APIKEYS].sudo()
        # Full rights let the key live until the computer signs out or is revoked; Odoo gives users only expiring keys.
        key = keys._generate(DEVICE_KEY_SCOPE, f"Medilab Sync: {name}", None)
        # Odoo does not return the row it inserted; it is the newest of the user's rows with the key's index.
        self.env.cr.execute(
            SQL(
                "SELECT max(id) FROM res_users_apikeys WHERE user_id = %s AND scope = %s AND index = %s",
                self.env.uid,
                DEVICE_KEY_SCOPE,
                key[:INDEX_SIZE],
            )
        )
        [(key_id,)] = self.env.cr.fetchall()
        return key, key_id

    def _seen(self):
        now = fields.Datetime.now()
        if not self.last_seen_at or now - self.last_seen_at >= SEEN_INTERVAL:
            self.sudo().last_seen_at = now
