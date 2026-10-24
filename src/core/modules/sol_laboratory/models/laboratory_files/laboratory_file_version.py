import posixpath

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, RESTORED, SYNCED, VERIFIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.fields.big_integer import BigInteger
from odoo.addons.sol_laboratory.services import laboratory_bucket

# A version's number, content and origin never change once it is stored. Other fields, such as the signing state a
# later feature adds, may.
PROTECTED_FIELDS = (
    "file_id",
    "number",
    "parent_version_id",
    "restored_from_id",
    "source",
    "size",
    "sha256",
    "content_id",
    "user_id",
    "device_id",
    "idempotency_key",
)


# Phiên Bản Tệp
class LaboratoryFileVersion(models.Model):
    _name = MODEL_LABORATORY_FILE_VERSION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _description = "Laboratory File Version"
    _order = "file_id, number desc"
    # Versions are stored by saving a file and are never changed or deleted.
    _permission_actions = ("read",)

    # The file.
    file_id = fields.Many2one(MODEL_LABORATORY_FILE, string="File", required=True, ondelete="restrict", readonly=True)
    # Version number within the file, never reused.
    number = fields.Integer(required=True, readonly=True)
    # The version that was current when this one was made.
    parent_version_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Parent Version", ondelete="restrict", readonly=True
    )
    # The version a restore copied.
    restored_from_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Restored From", ondelete="restrict", readonly=True
    )
    # synced, conflict, restored or edited_online.
    source = fields.Selection(
        [(SYNCED, "Synced"), (CONFLICT, "Conflict"), (RESTORED, "Restored"), (EDITED_ONLINE, "Edited Online")],
        required=True,
        readonly=True,
    )
    # Size of the content in bytes, as the server computed it.
    size = BigInteger(required=True, readonly=True)
    # SHA-256 of the content, in hexadecimal, as the server computed it.
    sha256 = fields.Char(string="SHA-256", required=True, readonly=True)
    # The verified content the version holds; versions with the same content share it.
    content_id = fields.Many2one(
        MODEL_LABORATORY_CONTENT, string="Content", required=True, ondelete="restrict", readonly=True, index=True
    )
    # The user who saved the version.
    user_id = fields.Many2one(MODEL_RES_USERS, string="Saved By", required=True, ondelete="restrict", readonly=True)
    # The device it came from; empty for a version made online or by a restore in the back office.
    device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, string="Computer", ondelete="restrict", readonly=True)

    _file_number_unique = models.Constraint("UNIQUE(file_id, number)", "A file has one version of each number.")
    _device_idempotency_key_unique = models.UniqueIndex(
        "(device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This computer already made a version with this Idempotency-Key.",
    )
    _sha256_format = models.Constraint(
        "CHECK(sha256 ~ '^[0-9a-f]{64}$')", "A version's SHA-256 is 64 lowercase hexadecimal digits."
    )
    _size_positive = models.Constraint("CHECK(size >= 0)", "A version's size cannot be negative.")

    @api.depends("file_id.path", "number")
    def _compute_display_name(self):
        for version in self:
            version.display_name = self.env._(
                "%(path)s, version %(number)s", path=version.file_id.path or "", number=version.number
            )

    @api.constrains("content_id", "sha256", "size")
    def _check_content(self):
        for version in self.sudo():
            content = version.content_id
            if content.state != VERIFIED or (content.sha256, content.size) != (version.sha256, version.size):
                raise ValidationError(
                    self.env._("A version holds verified content, with the size and SHA-256 the server computed.")
                )

    def _read_address(self, seconds):
        """The presigned address that reads the version's content for seconds, saved under its file's name. The caller
        checks first that the person may read the file."""
        self.ensure_one()
        version = self.sudo()
        name = posixpath.basename(version.file_id.path)
        return laboratory_bucket.read_address(version.content_id.object_key, seconds, name)

    def write(self, vals):
        if set(PROTECTED_FIELDS) & set(vals):
            raise UserError(
                self.env._("A version's number, content and origin never change; save the file again instead.")
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_version(self):
        raise UserError(self.env._("Versions of laboratory files are never deleted."))
