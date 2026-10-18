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
