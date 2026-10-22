import functools
import logging

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, UserError
from odoo.tools import SQL, mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DUPLICATE,
    FAILED,
    PENDING,
    SETTLE_CONTENT_CONTEXT,
    VERIFIED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.fields.big_integer import BigInteger
from odoo.addons.sol_laboratory.services import laboratory_bucket

_logger = logging.getLogger(__name__)

# What the server computed of the content, which only settling it sets.
COMPUTED_FIELDS = ("state", "size", "sha256")


# Nội Dung Lưu Trữ: one object in the laboratory files bucket, with the size and SHA-256 the server computed of it. Only
# full rights reach it, and its life is recorded through the versions and uploads that use it.
class LaboratoryContent(models.Model):
    _name = MODEL_LABORATORY_CONTENT
    _description = "Laboratory Content"
    _rec_name = "object_key"

    # Key of the object in the bucket: 32 hexadecimal digits the server made, which tell nothing about the content.
    object_key = fields.Char(required=True, readonly=True, copy=False)
    # pending, verified, duplicate or failed.
    state = fields.Selection(
        [(PENDING, "Pending"), (VERIFIED, "Verified"), (DUPLICATE, "Duplicate"), (FAILED, "Failed")],
        required=True,
        default=PENDING,
        readonly=True,
    )
    # Size of the content in bytes, as the server computed it; empty while pending.
    size = BigInteger(readonly=True)
    # SHA-256 of the content in hexadecimal, as the server computed it; empty while pending.
    sha256 = fields.Char(string="SHA-256", readonly=True)

    _object_key_unique = models.Constraint("UNIQUE(object_key)", "Each object of the bucket is one content.")
    _object_key_format = models.Constraint(
        "CHECK(object_key ~ '^[0-9a-f]{32}$')", "An object key is 32 lowercase hexadecimal digits."
    )
    _sha256_format = models.Constraint(
        "CHECK(sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$')", "A SHA-256 is 64 lowercase hexadecimal digits."
    )
    _size_positive = models.Constraint("CHECK(size IS NULL OR size >= 0)", "A content's size cannot be negative.")
    _computed_once_settled = models.Constraint(
        f"CHECK(state NOT IN ('{VERIFIED}', '{DUPLICATE}') OR (sha256 IS NOT NULL AND size IS NOT NULL))",
        "Verified content has the size and SHA-256 the server computed.",
    )
    _verified_sha256_unique = models.UniqueIndex(
        f"(sha256) WHERE state = '{VERIFIED}'", "Content with this SHA-256 is already stored."
    )

    @api.model_create_multi
    def create(self, vals_list):
        if any(set(COMPUTED_FIELDS) & set(vals) for vals in vals_list):
            raise UserError(self.env._("Content is pending until the server has computed its size and SHA-256."))
        return super().create(vals_list)

    def write(self, vals):
        if "object_key" in vals:
            raise UserError(self.env._("A content keeps the key of its object."))
        if set(COMPUTED_FIELDS) & set(vals) and not self.env.context.get(SETTLE_CONTENT_CONTEXT):
            raise UserError(self.env._("Content is settled by the server from its own reading of the bytes."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_content(self):
        raise UserError(self.env._("Stored content is never deleted."))

    @api.model
    def _new_pending(self):
        """A new pending content, under a new random key, for an object about to be written."""
        return self.sudo().create({"object_key": laboratory_bucket.new_object_key()}).with_env(self.env)

    def _settle(self, sha256, size):
        """Record the SHA-256 and size the server computed of the content's object, and return the verified content
        versions refer to: this one, or the content already stored with that SHA-256, when this one becomes a duplicate
        whose object is deleted after the commit. Settling it again returns the same content.

        Two contents of one SHA-256 settled at once keep one verified: the second fails on the unique index, and Odoo
        runs its request again, or its job item runs again, when it becomes the duplicate."""
        self.ensure_one()
        content = self.sudo()
        content._lock()
        if content.state == FAILED:
            raise UserError(self.env._("Failed content is never verified."))
        if content.state != PENDING:
            return content._canonical().with_env(self.env)
        settling = content.with_context(**{SETTLE_CONTENT_CONTEXT: True})
        canonical = self.sudo().search([("state", "=", VERIFIED), ("sha256", "=", sha256)], limit=1)
        if canonical:
            settling.write({"state": DUPLICATE, "sha256": sha256, "size": size})
            content._delete_object_after_commit()
            return canonical.with_env(self.env)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                settling.write({"state": VERIFIED, "sha256": sha256, "size": size})
                settling.flush_recordset()
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Committed by a transaction this one cannot see; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Content with the same SHA-256 was stored meanwhile; it is settled again.")
            ) from error
        return content.with_env(self.env)

    def _fail(self):
        """Mark pending content failed, such as content that is not what was claimed, and delete its object after the
        commit. Verified content is never failed."""
        content = self.sudo()
        content._lock()
        pending = content.filtered(lambda record: record.state == PENDING)
        if pending != content:
            raise UserError(self.env._("Only pending content fails."))
        pending.with_context(**{SETTLE_CONTENT_CONTEXT: True}).write({"state": FAILED})
        pending._delete_object_after_commit()

    def _canonical(self):
        """The verified content this one is or duplicates."""
        self.ensure_one()
        if self.state == VERIFIED:
            return self
        return self.search([("state", "=", VERIFIED), ("sha256", "=", self.sha256)], limit=1)

    def _lock(self):
        # The row is updated, as a file's is for a new version, so two settlings of one content are run one after the
        # other, the second again with what the first stored. Raw SQL, as the ORM only takes locks that do not wait.
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE medilab_laboratory_content SET write_date = %s, write_uid = %s WHERE id IN %s",
                fields.Datetime.now(),
                self.env.uid,
                tuple(self.ids),
            )
        )
        self.invalidate_recordset()

    def _delete_object_after_commit(self):
        # Only once the state that makes the object useless is committed: a rollback must leave the object in place.
        for key in self.mapped("object_key"):
            self.env.cr.postcommit.add(functools.partial(_delete_object, key))


def _delete_object(key):
    try:
        laboratory_bucket.delete(key)
    except Exception as error:
        # Reconciliation finds the object of failed and duplicate content still in the bucket and deletes it.
        _logger.warning("The object %s of laboratory content was not deleted: %s", key, type(error).__name__)
