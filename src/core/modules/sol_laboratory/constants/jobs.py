"""Context keys of scheduled jobs and what the cleanup job removes."""

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DOCUMENT_LOCK,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
)

# Context key holding the id of the job run a job's work is done in.
JOB_RUN_CONTEXT = "medilab_job_run_id"
# Context key with which the cleanup job removes archived audit entries; it takes effect only with full rights.
CLEANUP_CONTEXT = "medilab_cleanup"
# Key of the cleanup job.
CLEANUP_JOB = "cleanup"
# What the cleanup job removes: each kind, its model and the settings field holding its retention period in days.
CLEANUP_KINDS = {
    "job_items": (MODEL_JOB_ITEM, "job_retention_days"),
    "job_runs": (MODEL_JOB_RUN, "job_retention_days"),
    "locks": (MODEL_DOCUMENT_LOCK, "lock_retention_days"),
    "notifications": (MODEL_MAIL_NOTIFICATION, "notification_retention_days"),
    "devices": (MODEL_MOBILE_DEVICE, "device_retention_days"),
}
# Kind of the archive files the cleanup job writes of audit entries.
AUDIT_KIND = "audit_entry"
# Settings fields of the retention periods of what the cleanup job removes.
CLEANUP_RETENTION_FIELDS = tuple(dict.fromkeys(retention for _model, retention in CLEANUP_KINDS.values()))
