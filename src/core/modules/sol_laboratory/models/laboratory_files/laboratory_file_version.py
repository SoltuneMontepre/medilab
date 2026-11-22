import posixpath
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    CONFLICT,
    EDITED_ONLINE,
    GENERATED,
    RESTORED,
    RETENTION_REMOVAL_CONTEXT,
    SYNCED,
    VERIFIED,
)
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

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_file_version as LaboratoryFileVersionBase
else:
    LaboratoryFileVersionBase = object

# A version's number, content and origin never change once stored, except approved retention removal may detach its
# content while preserving its historical metadata. Other fields, such as signing state, may change.
PROTECTED_FIELDS = (
    "file_id",
    "number",
    "parent_version_id",
    "restored_from_id",
    "source",
    "size",
    "sha256",
    "content_id",
    "content_removed_at",
    "user_id",
    "device_id",
    "idempotency_key",
)


# Phiên Bản Tệp
class LaboratoryFileVersion(models.Model, LaboratoryFileVersionBase):
    _name = MODEL_LABORATORY_FILE_VERSION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _description = "Laboratory File Version"
    _order = "file_id, number desc"
    # Version history is immutable and never deleted; approved retention removal may detach the bytes.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The file.
        file_id = fields.Many2one(
            MODEL_LABORATORY_FILE, string="File", required=True, ondelete="restrict", readonly=True
        )
        # The folder of the file, which names the sample of a sample's folder.
        folder_id = fields.Many2one(related="file_id.folder_id")
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
        # synced, conflict, restored, edited_online or generated.
        source = fields.Selection(
            [
                (SYNCED, "Synced"),
                (CONFLICT, "Conflict"),
                (RESTORED, "Restored"),
                (EDITED_ONLINE, "Edited Online"),
                (GENERATED, "Generated"),
            ],
            required=True,
            readonly=True,
        )
        # Size of the content in bytes, as the server computed it.
        size = BigInteger(required=True, readonly=True)
        # SHA-256 of the content, in hexadecimal, as the server computed it.
        sha256 = fields.Char(string="SHA-256", required=True, readonly=True)
        # The verified content the version holds; retention removal clears it without removing the version history.
        content_id = fields.Many2one(
            MODEL_LABORATORY_CONTENT, string="Content", ondelete="restrict", readonly=True, index=True
        )
        # When approved retention removal detached this version from its stored content.
        content_removed_at = fields.Datetime(string="Content Removed On", readonly=True, copy=False)
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

    @api.constrains("content_id", "sha256", "size", "content_removed_at")
    def _check_content(self):
        for version in self.sudo():
            content = version.content_id
            if content and (
                content.state != VERIFIED or (content.sha256, content.size) != (version.sha256, version.size)
            ):
                raise ValidationError(
                    self.env._("A version holds verified content, with the size and SHA-256 the server computed.")
                )
            if not content and not version.content_removed_at:
                raise ValidationError(self.env._("A version without stored content must record its retention removal."))

    def _read_address(self, seconds):
        """The presigned address that reads the version's content for seconds, saved under its file's name. The caller
        checks first that the person may read the file."""
        self.ensure_one()
        version = self.sudo()
        if not version.content_id:
            raise UserError(self.env._("This version's content was removed after administrator approval."))
        name = posixpath.basename(version.file_id.path or "")
        return laboratory_bucket.read_address(version.content_id.object_key, seconds, name)

    def write(self, vals):
        if set(PROTECTED_FIELDS) & set(vals) and not (
            self.env.su
            and self.env.context.get(RETENTION_REMOVAL_CONTEXT)
            and set(vals) == {"content_id", "content_removed_at"}
            and not vals["content_id"]
            and vals["content_removed_at"]
            and not any(self.mapped("content_removed_at"))
        ):
            raise UserError(
                self.env._("A version's number, content and origin never change; save the file again instead.")
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_version(self):
        raise UserError(self.env._("Versions of laboratory files are never deleted."))
