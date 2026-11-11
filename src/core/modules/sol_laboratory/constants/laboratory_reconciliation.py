"""The reconciliation of the laboratory files bucket with stored content: its job, the marker that says which database
the bucket belongs to, and the kinds of what it finds."""

from datetime import timedelta

# The daily job that compares the bucket with the stored content.
RECONCILE_JOB = "laboratory_contents.reconcile"
# The object that holds the database.uuid of the database the bucket belongs to; it is no content.
MARKER_KEY = ".medilab-database"
# How old an object or a multipart upload must be before reconciliation acts on it, so it never touches the work of a
# transaction or a computer still in progress.
RECONCILE_AGE = timedelta(days=1)
# What reconciliation finds. It deletes the objects of no content, and the objects of duplicate and failed content that
# are still there; it aborts the multipart uploads of no open upload; it records the rest as errors.
NO_CONTENT = "object"
LEFT_BEHIND = "leftover"
MULTIPART = "multipart"
MISSING = "missing"
WRONG_SIZE = "size"
STALE_PENDING = "pending"
FOREIGN_MARKER = "marker"
