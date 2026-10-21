from . import (
    approval_chain,
    approval_level,
    archive_file,
    audit_change,
    audit_entry,
    audit_report,
    document_lock,
    hr_department,
    hr_employee,
    ir_access,
    ir_actions_act_window_view,
    ir_actions_report,
    ir_binary,
    ir_config_parameter,
    ir_mail_server,
    ir_ui_menu,
    ir_ui_view,
    job_item,
    job_run,
    mobile_device,
    permission,
    person,
    res_config_settings,
    res_partner,
    role,
    scheduled_job,
    signature,
)

# Accreditation and laboratory file lock job handlers inherit medilab.scheduled.job; load after the base model.
# isort: split
from . import accreditation_scheduled_job, laboratory_file_lock_scheduled_job
