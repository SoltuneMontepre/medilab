"""System parameters of the Laboratory module and their defaults."""

SAFETY_MARGIN_PARAMETER = "sol_laboratory.safety_margin_days"
DEFAULT_SAFETY_MARGIN_DAYS = 2
REMINDER_LEAD_PARAMETER = "sol_laboratory.reminder_lead_minutes"
DEFAULT_REMINDER_LEAD_MINUTES = 15
# No default: entries are kept for ever until a retention period is set.
AUDIT_RETENTION_PARAMETER = "sol_laboratory.audit_retention_days"
