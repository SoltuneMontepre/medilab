"""Statuses of uploads of laboratory files, why one failed or was refused, the jobs that verify, store and expire them,
and the codes of the refusals of the upload routes."""

# The statuses of an upload.
PREPARED = "prepared"
VERIFYING = "verifying"
COMPLETED = "completed"
UPLOAD_CONFLICT = "conflict"
UNCHANGED = "unchanged"
REFUSED = "refused"
UPLOAD_FAILED = "failed"
UPLOAD_EXPIRED = "expired"
# Uploads that end no more: they become nothing else.
ENDED_STATUSES = (COMPLETED, UPLOAD_CONFLICT, UNCHANGED, UPLOAD_FAILED, UPLOAD_EXPIRED)
# Uploads the computer finalizes: prepared ones, and refused ones once what refused them is gone.
FINALIZED_STATUSES = (PREPARED, REFUSED)
# Why the content of an upload failed: its size or its SHA-256 is not the one claimed, or no object was completed.
SIZE_MISMATCH = "size_mismatch"
SHA256_MISMATCH = "sha256_mismatch"
MISSING_OBJECT = "missing_object"
# The jobs that verify an upload's content by reading its object, store its version, and expire unfinished uploads.
VERIFY_JOB = "laboratory_contents.verify"
STORE_JOB = "laboratory_uploads.store"
EXPIRE_JOB = "laboratory_uploads.expire"
# Codes of the refusals of finalizing an upload whose parts are not all uploaded, of an upload that takes no more parts
# or finalizing, and of a call while the bucket cannot be reached.
UPLOAD_INCOMPLETE = "upload_incomplete"
UPLOAD_CLOSED = "upload_closed"
STORAGE_UNAVAILABLE = "storage_unavailable"
# The most part addresses one call gives.
MAX_PART_ADDRESSES = 100
