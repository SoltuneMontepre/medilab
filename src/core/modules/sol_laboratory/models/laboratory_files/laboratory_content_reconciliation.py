import logging

from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.laboratory_files import DUPLICATE, FAILED, PENDING, VERIFIED
from odoo.addons.sol_laboratory.constants.laboratory_reconciliation import (
    FOREIGN_MARKER,
    LEFT_BEHIND,
    MARKER_KEY,
    MISSING,
    MULTIPART,
    NO_CONTENT,
    RECONCILE_AGE,
    STALE_PENDING,
    WRONG_SIZE,
)
from odoo.addons.sol_laboratory.constants.laboratory_uploads import ENDED_STATUSES
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_UPLOAD,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

_logger = logging.getLogger(__name__)

# The method that acts on each kind of finding.
HANDLERS = {
    NO_CONTENT: "_delete_object_of_no_content",
    LEFT_BEHIND: "_delete_object_left_behind",
    MULTIPART: "_abort_multipart_of_no_upload",
    MISSING: "_record_missing_object",
    WRONG_SIZE: "_record_wrong_size",
    STALE_PENDING: "_record_stale_pending",
}


# Nội Dung Lưu Trữ: the daily comparison of the bucket with the stored content.
class LaboratoryContent(models.Model):
    _inherit = MODEL_LABORATORY_CONTENT

    @api.model
    def _database_uuid(self):
        return self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str("database.uuid")

    @api.model
    def _bucket_owner(self):
        """The database.uuid of the database the bucket belongs to, from its marker. A bucket without one is marked as
        this database's: Garage takes no conditional write, so it is a read then a write, which only this job makes."""
        owner = laboratory_bucket.read_text(MARKER_KEY)
        if owner is None:
            owner = self._database_uuid()
            laboratory_bucket.write_text(MARKER_KEY, owner)
        return owner.strip()

    @api.model
    def _reconcile_findings(self):
        """What the bucket and the stored content disagree on, as (item key, payload). A bucket that belongs to another
        database, such as one restored from production into staging, gives that finding only, so nothing is deleted
        from it."""
        owner = self._bucket_owner()
        if owner != self._database_uuid():
            yield f"{FOREIGN_MARKER}:{owner}", {"kind": FOREIGN_MARKER, "uuid": owner}
            return
        cutoff = fields.Datetime.now() - RECONCILE_AGE
        yield from self._object_findings(cutoff)
        yield from self._pending_findings(cutoff)
        yield from self._multipart_findings(cutoff)

    @api.model
    def _object_findings(self, cutoff):
        # The bucket lists its objects in the order of their keys, and the rows come in the same order, so the two are
        # walked side by side without holding either whole.
        rows = self._rows_by_key()
        row = next(rows, None)
        for key, size, modified in laboratory_bucket.objects():
            if key == MARKER_KEY:
                continue
            while row and row[0] < key:
                yield from self._row_without_object(row)
                row = next(rows, None)
            if row and row[0] == key:
                yield from self._row_with_object(row, size, modified, cutoff)
                row = next(rows, None)
            elif modified < cutoff:
                yield f"{NO_CONTENT}:{key}", {"kind": NO_CONTENT, "key": key}
        while row:
            yield from self._row_without_object(row)
            row = next(rows, None)

    @api.model
    def _rows_by_key(self):
        # Keys are lowercase hexadecimal, which byte order sorts as the bucket does.
        self.flush_model(["object_key", "state", "size"])
        self.env.cr.execute(
            SQL('SELECT object_key, state, size FROM medilab_laboratory_content ORDER BY object_key COLLATE "C"')
        )
        return iter(self.env.cr.fetchall())

    @api.model
    def _row_without_object(self, row):
        key, state, _size = row
        if state == VERIFIED:
            yield f"{MISSING}:{key}", {"kind": MISSING, "key": key}

    @api.model
    def _row_with_object(self, row, size, modified, cutoff):
        key, state, expected = row
        if state in (DUPLICATE, FAILED) and modified < cutoff:
            yield f"{LEFT_BEHIND}:{key}", {"kind": LEFT_BEHIND, "key": key}
        elif state == VERIFIED and size != expected:
            yield f"{WRONG_SIZE}:{key}", {"kind": WRONG_SIZE, "key": key}

    @api.model
    def _pending_findings(self, cutoff):
        stale = self.sudo().search(
            [("state", "=", PENDING), ("create_date", "<", cutoff), ("id", "not in", self._open_upload_contents().ids)]
        )
        for content in stale:
            yield f"{STALE_PENDING}:{content.id}", {"kind": STALE_PENDING, "key": content.object_key}

    @api.model
    def _multipart_findings(self, cutoff):
        open_multiparts = set(self._open_uploads().mapped("multipart_id"))
        for key, upload_id, initiated in laboratory_bucket.multipart_uploads():
            if initiated < cutoff and upload_id not in open_multiparts:
                yield f"{MULTIPART}:{upload_id}", {"kind": MULTIPART, "key": key, "upload_id": upload_id}

    @api.model
    def _open_uploads(self):
        # Uploads not ended, the refused ones a computer may finalize again among them, still need their content and
        # their multipart upload.
        return self.env[MODEL_LABORATORY_UPLOAD].sudo().search([("status", "not in", ENDED_STATUSES)])

    @api.model
    def _open_upload_contents(self):
        return self._open_uploads().content_id

    @api.model
    def _reconcile(self, payload):
        """Act on a finding once the bucket still belongs to this database and the finding still holds, as the content
        or the upload may have changed since the bucket was listed."""
        if payload["kind"] == FOREIGN_MARKER:
            self._record_error(
                self.env._(
                    "The laboratory files bucket belongs to the database %(uuid)s, so reconciliation deletes nothing "
                    "in it.",
                    uuid=payload["uuid"],
                )
            )
            return
        if self._bucket_owner() != self._database_uuid():
            return
        getattr(self, HANDLERS[payload["kind"]])(payload)

    @api.model
    def _content_of(self, key):
        return self.sudo().search([("object_key", "=", key)], limit=1)

    @api.model
    def _delete_object_of_no_content(self, payload):
        if not self._content_of(payload["key"]):
            laboratory_bucket.delete(payload["key"])
            _logger.info("Deleted the object %s of the laboratory files bucket, which no content has", payload["key"])

    @api.model
    def _delete_object_left_behind(self, payload):
        if self._content_of(payload["key"]).state in (DUPLICATE, FAILED):
            laboratory_bucket.delete(payload["key"])
            _logger.info("Deleted the object %s of duplicate or failed laboratory content", payload["key"])

    @api.model
    def _abort_multipart_of_no_upload(self, payload):
        if payload["upload_id"] not in self._open_uploads().mapped("multipart_id"):
            laboratory_bucket.abort_upload(payload["key"], payload["upload_id"])
            _logger.info("Aborted the multipart upload %s, which no open upload has", payload["upload_id"])

    @api.model
    def _record_missing_object(self, payload):
        content = self._content_of(payload["key"])
        if content.state == VERIFIED and laboratory_bucket.object_size(content.object_key) is None:
            self._record_error(
                self.env._(
                    "The object %(key)s of verified laboratory file content is missing from the bucket.",
                    key=content.object_key,
                )
            )

    @api.model
    def _record_wrong_size(self, payload):
        content = self._content_of(payload["key"])
        size = laboratory_bucket.object_size(content.object_key) if content.state == VERIFIED else None
        if size is not None and size != content.size:
            self._record_error(
                self.env._(
                    "The object %(key)s of verified laboratory file content has %(size)s bytes instead of %(expected)s.",
                    key=content.object_key,
                    size=size,
                    expected=content.size,
                )
            )

    @api.model
    def _record_stale_pending(self, payload):
        content = self._content_of(payload["key"])
        if content.state == PENDING and content not in self._open_upload_contents():
            self._record_error(
                self.env._(
                    "The laboratory file content %(key)s is still pending a day after it was made, and no open upload "
                    "holds it.",
                    key=content.object_key,
                )
            )

    @api.model
    def _record_error(self, note):
        # Content is not audited, so what reconciliation finds is an error of the system.
        self.env[MODEL_AUDIT_ENTRY]._log_event("error", note)
