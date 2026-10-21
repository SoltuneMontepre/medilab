import contextlib
import hashlib
from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.laboratory_api import TRY_AGAIN_SECONDS
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PART_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    CONFLICT,
    DEVICE_REVOKED,
    FILE_READ,
    FILE_WRITE,
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    NOT_FOUND,
    PENDING,
    SYNCED,
)
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    FINALIZED_STATUSES,
    MAX_PART_ADDRESSES,
    MISSING_OBJECT,
    PREPARED,
    REFUSED,
    SHA256_MISMATCH,
    SIZE_MISMATCH,
    STORAGE_UNAVAILABLE,
    STORE_JOB,
    UNCHANGED,
    UPLOAD_CLOSED,
    UPLOAD_CONFLICT,
    UPLOAD_EXPIRED,
    UPLOAD_FAILED,
    UPLOAD_INCOMPLETE,
    VERIFY_JOB,
    VERIFYING,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_JOB_ITEM,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_UPLOAD,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.laboratory_paths import is_relative_path, normal_text, path_key

# The SHA-256 of empty content, the only one an empty file can claim.
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


# Tải Lên Tệp: preparing, finalizing, verifying, storing and expiring an upload. Every bucket call here is safe to make
# twice, as Odoo runs a request again after a concurrency failure and a job item that fails runs again later.
class LaboratoryUploadFlow(models.Model):
    _inherit = MODEL_LABORATORY_UPLOAD

    @api.model
    def _prepare(self, device, folder, path, size, sha256, base_version_id, key):
        """The upload of the content the computer claims, at the path of the folder, from the base version, once the
        person may write the file there; a lock refuses it before any byte is sent. A request repeated with its
        Idempotency-Key gets the upload it made. When the file's current version has the claimed SHA-256 nothing is
        uploaded; otherwise the content goes to a new object under a random key, in the parts of a multipart upload the
        server creates, even when the same content is stored already for this file or another."""
        path = normal_text(path)
        if not is_relative_path(path):
            raise LaboratoryFileError(
                INVALID_REQUEST, self.env._("A path is relative to its folder, such as HPLC/run-01.csv: %s", path)
            )
        files = self.env[MODEL_LABORATORY_FILE].sudo()
        file = files.search([("folder_id", "=", folder.id), ("path_key", "=", path_key(path))], limit=1)
        if file:
            file.with_env(self.env)._check_file_access(FILE_WRITE)
        else:
            folder._check_folder_access(FILE_WRITE)
        base_version = self._base_version(file, base_version_id)
        created = self._created_with_key(device, key)
        if created:
            if not created._is_request(folder, path, size, sha256, base_version):
                raise LaboratoryFileError(
                    IDEMPOTENCY_CONFLICT, self.env._("This Idempotency-Key was already sent with another request.")
                )
            return created
        values = {
            "folder_id": folder.id,
            "file_id": file.id,
            "path": file.path or path,
            "base_version_id": base_version.id,
            "claimed_size": size,
            "claimed_sha256": sha256,
            "user_id": self.env.uid,
            "expires_at": fields.Datetime.now() + timedelta(hours=self._upload_hours()),
        }
        if file and file.current_version_id.sha256 == sha256:
            return self.sudo()._create_once(device, key, {**values, "status": UNCHANGED}).with_env(self.env)
        if size == 0 and sha256 != EMPTY_SHA256:
            raise LaboratoryFileError(INVALID_REQUEST, self.env._("Empty content has the SHA-256 %s.", EMPTY_SHA256))
        content = self.env[MODEL_LABORATORY_CONTENT].sudo()._new_pending()
        with _bucket_refusal(self.env):
            if size == 0:
                # A multipart upload has at least one part of at least one byte, so the server writes empty content.
                laboratory_bucket.write(content.object_key, iter(()))
                multipart_id = False
            else:
                multipart_id = laboratory_bucket.create_upload(content.object_key)
        values.update(content_id=content.id, multipart_id=multipart_id)
        return self.sudo()._create_once(device, key, values).with_env(self.env)

    @api.model
    def _base_version(self, file, base_version_id):
        if not base_version_id:
            return self.env[MODEL_LABORATORY_FILE_VERSION]
        version = self.env[MODEL_LABORATORY_FILE_VERSION].sudo().browse(base_version_id).exists()
        if not version or version.file_id != file:
            raise LaboratoryFileError(INVALID_REQUEST, self.env._("The base version is not a version of this file."))
        return version

    @api.model
    def _upload_hours(self):
        return self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_upload_hours")

    def _is_request(self, folder, path, size, sha256, base_version):
        """Whether the upload is the one of this request: the same path of the same folder, content and base version."""
        upload = self.sudo()
        return (upload.folder_id, path_key(upload.path), upload.claimed_size, upload.claimed_sha256) == (
            folder.sudo(),
            path_key(path),
            size,
            sha256,
        ) and upload.base_version_id == base_version.sudo()

    @api.model
    def _checked_for(self, device, folder_id, upload_id):
        """The upload of the id that the computer made in the folder, once the person may still read the folder. Another
        computer's upload is not found."""
        upload = self.sudo().browse(upload_id).exists()
        if not upload or upload.device_id != device or upload.folder_id.id != folder_id:
            raise LaboratoryFileError(
                NOT_FOUND, self.env._("This upload does not exist or you do not have access to it.")
            )
        upload = upload.with_env(self.env)
        upload._check_access(FILE_READ)
        return upload

    def _check_access(self, access):
        """Check that the person may read or write the upload's file, or its folder while the path has no file; a file
        saved at the path since the upload was prepared is checked with its locks."""
        self.ensure_one()
        upload = self.sudo()
        file = upload.file_id or upload._file_at_path()
        if file:
            file.with_env(self.env)._check_file_access(access)
        else:
            upload.folder_id.with_env(self.env)._check_folder_access(access)

    def _file_at_path(self):
        files = self.env[MODEL_LABORATORY_FILE].sudo()
        return files.search([("folder_id", "=", self.folder_id.id), ("path_key", "=", path_key(self.path))], limit=1)

    def _check_open(self):
        """Refuse a part address or finalizing an upload that takes no more parts: not prepared, or past its expiry."""
        self.ensure_one()
        upload = self.sudo()
        if upload.status not in FINALIZED_STATUSES or upload.expires_at <= fields.Datetime.now():
            raise LaboratoryFileError(UPLOAD_CLOSED, self.env._("This upload is closed; prepare the file again."))

    def _part_addresses(self, numbers):
        """The presigned addresses that upload the parts of the numbers, once the person may still write the file, and
        when they stop working: after the file address lifetime of the settings, or the upload's expiry if sooner."""
        self.ensure_one()
        upload = self.sudo()
        upload._check_open()
        if upload.status != PREPARED or not upload.multipart_id:
            raise LaboratoryFileError(UPLOAD_CLOSED, self.env._("This upload takes no more parts."))
        self._check_access(FILE_WRITE)
        count = upload._part_count()
        if len(numbers) > MAX_PART_ADDRESSES or any(not 1 <= number <= count for number in numbers):
            raise LaboratoryFileError(
                INVALID_REQUEST,
                self.env._(
                    "Ask for at most %(most)s parts, numbered from 1 to %(count)s.",
                    most=MAX_PART_ADDRESSES,
                    count=count,
                ),
            )
        now = fields.Datetime.now()
        minutes = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_file_url_minutes")
        expires_at = min(now + timedelta(minutes=minutes), upload.expires_at)
        seconds = max(int((expires_at - now).total_seconds()), 1)
        key = upload.content_id.object_key
        addresses = [
            (number, laboratory_bucket.part_address(key, upload.multipart_id, number, seconds))
            for number in sorted(set(numbers))
        ]
        return addresses, expires_at

    def _finalize(self):
        """Finalize the upload once every part is uploaded and the person may still write the file, and queue its
        verification, or for a refused upload its storing again. An upload already past finalizing answers with its
        state, as the computer repeats a call whose answer it lost."""
        self.ensure_one()
        upload = self.sudo()
        upload._lock()
        if upload.status not in FINALIZED_STATUSES:
            return self
        upload._check_open()
        self._check_access(FILE_WRITE)
        if upload.status == PREPARED and upload.multipart_id:
            upload._check_parts()
        upload.write({"status": VERIFYING, "finalized_at": fields.Datetime.now(), "failure_code": False})
        if upload.content_id.state == PENDING:
            upload._queue(VERIFY_JOB, f"content:{upload.content_id.id}")
        else:
            upload._queue_store()
        return self

    def _check_parts(self):
        # Every part is there with its size: all of PART_SIZE bytes but the last. The bytes themselves are checked
        # by reading the object once the upload is completed, never by its ETags.
        with _bucket_refusal(self.env):
            try:
                parts = laboratory_bucket.uploaded_parts(self.content_id.object_key, self.multipart_id)
            except laboratory_bucket.UploadNotFound as error:
                raise LaboratoryFileError(
                    UPLOAD_CLOSED, self.env._("This upload is closed; prepare the file again.")
                ) from error
        count = self._part_count()
        expected = [(number, PART_SIZE) for number in range(1, count)]
        expected.append((count, self.claimed_size - (count - 1) * PART_SIZE))
        if [(number, size) for number, size, _etag in parts] != expected:
            raise LaboratoryFileError(
                UPLOAD_INCOMPLETE,
                self.env._("Upload every part before finalizing: %s parts are expected.", count),
            )

    def _queue(self, job_key, item_key):
        jobs = self.env[MODEL_SCHEDULED_JOB].sudo()
        jobs.queue(job_key, item_key, document=self)
        jobs._by_key(job_key).cron_id._trigger()

    def _queue_store(self):
        # One item per storing the upload is finalized for, so a refused upload finalized again is stored again.
        job = self.env[MODEL_SCHEDULED_JOB].sudo()._by_key(STORE_JOB)
        queued = (
            self.env[MODEL_JOB_ITEM]
            .sudo()
            .search_count([("job_id", "=", job.id), ("document_model", "=", self._name), ("document_id", "=", self.id)])
        )
        self._queue(STORE_JOB, f"upload:{self.id}:{queued + 1}")

    def _verify(self):
        """Complete the upload, then read its object from the first byte and compute its size and SHA-256: content
        whose size or SHA-256 is not the claim fails, with the upload; otherwise it is settled, as verified or as a
        duplicate of content already stored, and the upload's version is queued for storing. A verification stopped
        midway leaves the content pending, and the next one reads the object from the first byte again."""
        self.ensure_one()
        upload = self.sudo()
        content = upload.content_id
        if upload.status != VERIFYING:
            return
        if content.state != PENDING:
            upload._queue_store()
            return
        if not upload._complete():
            upload._fail(MISSING_OBJECT)
            return
        digest = hashlib.sha256()
        size = 0
        with laboratory_bucket.read(content.object_key) as chunks:
            for chunk in chunks:
                digest.update(chunk)
                size += len(chunk)
                if size > upload.claimed_size:
                    break
        if size != upload.claimed_size:
            upload._fail(SIZE_MISMATCH)
        elif digest.hexdigest() != upload.claimed_sha256:
            upload._fail(SHA256_MISMATCH)
        else:
            content._settle(upload.claimed_sha256, size)
            upload._queue_store()

    def _complete(self):
        # Whether the object is there to read: empty content the server wrote, or the multipart upload completed now or
        # by an earlier run, when the bucket no longer knows the upload but has its object.
        key = self.content_id.object_key
        if not self.multipart_id:
            return laboratory_bucket.object_size(key) is not None
        try:
            parts = laboratory_bucket.uploaded_parts(key, self.multipart_id)
        except laboratory_bucket.UploadNotFound:
            return laboratory_bucket.object_size(key) is not None
        try:
            laboratory_bucket.complete_upload(key, self.multipart_id, [(number, etag) for number, _size, etag in parts])
        except laboratory_bucket.UploadNotFound:
            return False
        return True

    def _fail(self, code):
        """End the upload in failure, with its content and its object."""
        self.ensure_one()
        if self.content_id.state == PENDING:
            self.content_id._fail()
        self.write({"status": UPLOAD_FAILED, "failure_code": code})

    def _store(self):
        """Store the version of the verified content, as the person who uploaded it from their computer, once they may
        still write the file. Storing it again stores nothing, as the upload's row is updated before its status is
        read; a refusal is the upload's, and the computer may finalize it again before it expires."""
        self.ensure_one()
        upload = self.sudo()
        upload._lock()
        if upload.status != VERIFYING:
            return
        try:
            with self.env.cr.savepoint():
                file, current, version = upload._store_as_uploader()
        except LaboratoryFileError as error:
            upload._refuse(error.code)
            return
        values = {"file_id": file.id} if not upload.file_id else {}
        if version == current:
            values["status"] = UNCHANGED
        else:
            values.update(status=UPLOAD_CONFLICT if version.source == CONFLICT else COMPLETED, version_id=version.id)
        upload.write(values)

    def _store_as_uploader(self):
        # The checks of the person who uploaded, in their own environment, then the version of the canonical content:
        # the file, its version current before, and the version stored or the current one when it had the content.
        uploader = self.user_id
        if self.device_id.revoked_at:
            raise LaboratoryFileError(DEVICE_REVOKED, self.env._("The computer was revoked meanwhile."))
        folder = self.folder_id.with_user(uploader)
        if not self.file_id:
            folder._check_folder_access(FILE_WRITE)
        file = self.env[MODEL_LABORATORY_FILE].with_user(uploader)._get_or_create(folder, self.path)
        file._check_file_access(FILE_WRITE)
        current = file.sudo().current_version_id
        version = file._add_version(
            content=self.content_id._canonical(),
            source=SYNCED,
            user=uploader,
            device=self.device_id,
            base_version=self.base_version_id,
        )
        return file, current, version

    def _refuse(self, code):
        """Record that storing the upload's version was refused, with the code of the refusal: a lock someone else holds,
        a folder archived or turned off, the person no longer a member, or the computer revoked. Its verified content
        is kept, and the computer may finalize the upload again until it expires."""
        self.ensure_one()
        self.write({"status": REFUSED, "failure_code": code})

    @api.model
    def _unfinished(self):
        """The uploads past their expiry that were never stored: prepared, or refused."""
        return self.sudo().search([("status", "in", FINALIZED_STATUSES), ("expires_at", "<=", fields.Datetime.now())])

    def _expire(self):
        """Expire the upload once it is past its expiry and was never stored: abort its multipart upload, which
        removes its parts, and fail its content when it is still pending. Verified content is never touched."""
        self.ensure_one()
        upload = self.sudo()
        upload._lock()
        if upload.status not in FINALIZED_STATUSES or upload.expires_at > fields.Datetime.now():
            return
        content = upload.content_id
        if content.state == PENDING:
            if upload.multipart_id:
                laboratory_bucket.abort_upload(content.object_key, upload.multipart_id)
            content._fail()
        upload.write({"status": UPLOAD_EXPIRED})

    def _laboratory_api_values(self):
        """The upload as the laboratory files API gives it to the computer that made it. Its content's state and key
        are never given, so the answer tells nothing of content stored for other files."""
        self.ensure_one()
        upload = self.sudo()
        version = upload.version_id or (upload.file_id.current_version_id if upload.status == UNCHANGED else False)
        return {
            "id": upload.id,
            "path": upload.path,
            "status": upload.status,
            "failure_code": upload.failure_code or None,
            "size": upload.claimed_size,
            "sha256": upload.claimed_sha256,
            "base_version_id": upload.base_version_id.id or None,
            "part_size": PART_SIZE,
            "part_count": upload._part_count() if upload.multipart_id else 0,
            "expires_at": api_datetime(upload.expires_at),
            "version": version.with_env(self.env)._laboratory_api_values() if version else None,
        }


@contextlib.contextmanager
def _bucket_refusal(env):
    """Answer a bucket that cannot be reached now with storage_unavailable, which the computer tries again after."""
    try:
        yield
    except laboratory_bucket.BucketUnavailable as error:
        raise LaboratoryFileError(
            STORAGE_UNAVAILABLE,
            env._("The laboratory files bucket cannot be reached; try again shortly."),
            retry_after=TRY_AGAIN_SECONDS,
        ) from error
