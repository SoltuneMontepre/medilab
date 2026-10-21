"""System parameters of the Laboratory module and their defaults."""

SAFETY_MARGIN_PARAMETER = "sol_laboratory.safety_margin_days"
DEFAULT_SAFETY_MARGIN_DAYS = 2
REMINDER_LEAD_PARAMETER = "sol_laboratory.reminder_lead_minutes"
DEFAULT_REMINDER_LEAD_MINUTES = 15
# No default: entries are kept for ever until a retention period is set.
AUDIT_RETENTION_PARAMETER = "sol_laboratory.audit_retention_days"
SAMPLE_RETENTION_REMINDER_PARAMETER = "sol_laboratory.sample_retention_reminder_days"
DEFAULT_SAMPLE_RETENTION_REMINDER_DAYS = 7
URGENCY_HOURS_PARAMETER = "sol_laboratory.urgency_hours"
DEFAULT_URGENCY_HOURS = 24
DIGITAL_SIGNING_PARAMETER = "sol_laboratory.digital_signing_enabled"
SIGNING_CERTIFICATE_ALERT_PARAMETER = "sol_laboratory.signing_certificate_alert_days"
DEFAULT_SIGNING_CERTIFICATE_ALERT_DAYS = 30
LOCK_TIMEOUT_PARAMETER = "sol_laboratory.lock_timeout_minutes"
DEFAULT_LOCK_TIMEOUT_MINUTES = 15
JOB_RETENTION_PARAMETER = "sol_laboratory.job_retention_days"
LOCK_RETENTION_PARAMETER = "sol_laboratory.lock_retention_days"
NOTIFICATION_RETENTION_PARAMETER = "sol_laboratory.notification_retention_days"
DEVICE_RETENTION_PARAMETER = "sol_laboratory.device_retention_days"
# Days the cleanup job keeps finished job items and runs, ended locks, read notifications and turned-off devices.
DEFAULT_RETENTION_DAYS = 90
LABORATORY_FOLDER_RETENTION_PARAMETER = "sol_laboratory.laboratory_folder_retention_days"
# Five years, assumed until the laboratory gives a period: no document sets how long laboratory files are kept.
DEFAULT_LABORATORY_FOLDER_RETENTION_DAYS = 1825
LABORATORY_FILE_LOCK_PARAMETER = "sol_laboratory.laboratory_file_lock_minutes"
DEFAULT_LABORATORY_FILE_LOCK_MINUTES = 30
