import math
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.laboratory_bucket import PART_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    PREPARED,
    REFUSED,
    UNCHANGED,
    UPLOAD_CONFLICT,
    UPLOAD_EXPIRED,
    UPLOAD_FAILED,
    VERIFYING,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_LABORATORY_UPLOAD,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.fields.big_integer import BigInteger

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_laboratory_upload as LaboratoryUploadBase
else:
    LaboratoryUploadBase = object

# What the computer asked to upload, and the object it uploads to, which never change.
IDENTITY_FIELDS = (
    "folder_id",
    "path",
    "base_version_id",
    "claimed_size",
    "claimed_sha256",
    "content_id",
    "multipart_id",
    "user_id",
    "device_id",
    "expires_at",
)
# The statuses each status moves on to.
NEXT_STATUSES = {
    PREPARED: frozenset({VERIFYING, UPLOAD_EXPIRED}),
    VERIFYING: frozenset({COMPLETED, UPLOAD_CONFLICT, UNCHANGED, REFUSED, UPLOAD_FAILED}),
    REFUSED: frozenset({VERIFYING, UPLOAD_EXPIRED}),
    COMPLETED: frozenset(),
    UPLOAD_CONFLICT: frozenset(),
    UNCHANGED: frozenset(),
    UPLOAD_FAILED: frozenset(),
    UPLOAD_EXPIRED: frozenset(),
}
# Five gibibytes, the largest file uploaded.
MAX_SIZE = 5 * 1024**3


# Tải Lên Tệp: a computer uploading a file's content straight to the bucket, in the parts of a multipart upload the
# server made, from the version the computer's file was based on.
class LaboratoryUpload(models.Model, LaboratoryUploadBase):
    _name = MODEL_LABORATORY_UPLOAD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _description = "Laboratory Upload"
    _order = "id desc"
    _rec_name = "path"
    # Computers make uploads through the laboratory files API, and the server moves them on; they are never deleted.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The folder uploaded to.
        folder_id = fields.Many2one(
            MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="restrict", readonly=True
        )
        # The file, once known; empty for a new path until its version is stored.
        file_id = fields.Many2one(MODEL_LABORATORY_FILE, string="File", ondelete="restrict", readonly=True)
        # Path of the file relative to the folder, in Unicode NFC.
        path = fields.Char(required=True, readonly=True)
        # The version the computer's file was based on; empty for a new file.
        base_version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="Base Version", ondelete="restrict", readonly=True
        )
        # Size of the content in bytes, as the computer claims it.
        claimed_size = BigInteger(required=True, readonly=True)
        # SHA-256 of the content in hexadecimal, as the computer claims it.
        claimed_sha256 = fields.Char(string="Claimed SHA-256", required=True, readonly=True)
        # The content of the upload's own object; empty when the file already had the content and nothing was uploaded.
        content_id = fields.Many2one(MODEL_LABORATORY_CONTENT, string="Content", ondelete="restrict", readonly=True)
        # The bucket's id of the multipart upload; empty when nothing was uploaded in parts.
        multipart_id = fields.Char(readonly=True, copy=False)
        # prepared, verifying, completed, conflict, unchanged, refused, failed or expired.
        status = fields.Selection(
            [
                (PREPARED, "Prepared"),
                (VERIFYING, "Verifying"),
                (COMPLETED, "Completed"),
                (UPLOAD_CONFLICT, "Conflict"),
                (UNCHANGED, "Unchanged"),
                (REFUSED, "Refused"),
                (UPLOAD_FAILED, "Failed"),
                (UPLOAD_EXPIRED, "Expired"),
            ],
            required=True,
            default=PREPARED,
            readonly=True,
        )
        # Why the upload failed or was refused, as the code a computer acts on.
        failure_code = fields.Char(readonly=True)
        # The version the upload stored.
        version_id = fields.Many2one(
            MODEL_LABORATORY_FILE_VERSION, string="Version", ondelete="restrict", readonly=True, copy=False
        )
        # The user uploading.
        user_id = fields.Many2one(
            MODEL_RES_USERS, string="Uploaded By", required=True, ondelete="restrict", readonly=True
        )
        # The computer uploading.
        device_id = fields.Many2one(
            MODEL_LABORATORY_DEVICE, string="Computer", required=True, ondelete="restrict", readonly=True
        )
        # When an upload not finalized by then expires and its parts are removed.
        expires_at = fields.Datetime(required=True, readonly=True)
        # When the computer last finalized the upload.
        finalized_at = fields.Datetime(readonly=True, copy=False)

    _device_idempotency_key_unique = models.UniqueIndex(
        "(device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This computer already prepared an upload with this Idempotency-Key.",
    )
    _version_unique = models.Constraint("UNIQUE(version_id)", "A version is stored by one upload only.")
    _claimed_sha256_format = models.Constraint(
        "CHECK(claimed_sha256 ~ '^[0-9a-f]{64}$')", "A SHA-256 is 64 lowercase hexadecimal digits."
    )
    _claimed_size_range = models.Constraint(
        f"CHECK(claimed_size >= 0 AND claimed_size <= {MAX_SIZE})", "A file uploaded is at most 5 GiB."
    )
    _status_expiry_index = models.Index("(status, expires_at)")

    @api.depends("path", "status")
    def _compute_display_name(self):
        statuses = dict(self._fields["status"]._description_selection(self.env))
        for upload in self:
            upload.display_name = self.env._(
                "%(path)s, %(status)s", path=upload.path or "", status=statuses.get((upload.status or ""), "")
            )

    def write(self, vals):
        if set(IDENTITY_FIELDS) & set(vals):
            raise UserError(self.env._("An upload keeps what was asked to upload and the object it uploads to."))
        if "file_id" in vals and any(upload.file_id for upload in self):
            raise UserError(self.env._("An upload keeps its file."))
        if "status" in vals and any(
            vals["status"] != upload.status and vals["status"] not in NEXT_STATUSES[upload.status or ""]
            for upload in self
        ):
            raise UserError(self.env._("An upload moves on only as the server verifies and stores it."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_upload(self):
        raise UserError(self.env._("Uploads of laboratory files are never deleted."))

    def _audit_parents(self):
        return {
            upload.id: (MODEL_LABORATORY_FILE, upload.file_id.id)
            if upload.file_id
            else (MODEL_LABORATORY_FOLDER, upload.folder_id.id)
            for upload in self.sudo()
        }

    def _part_count(self):
        """The number of parts of the upload: every part but the last is PART_SIZE bytes; empty content has none."""
        self.ensure_one()
        return math.ceil(self.claimed_size / PART_SIZE)

    def _lock(self):
        # The row is updated, as a file's is for a new version, so two finalizations or storings of one upload are run
        # one after the other, the second again with what the first did. Raw SQL, as the ORM only takes locks that do
        # not wait.
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE medilab_laboratory_upload SET write_date = %s, write_uid = %s WHERE id IN %s",
                fields.Datetime.now(),
                self.env.uid,
                tuple(self.ids),
            )
        )
        self.invalidate_recordset()
