from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_RUN, MODEL_SCHEDULED_JOB
from odoo.addons.sol_onboarding.constants.onboarding import JOB_KEY_PREFIX


def uninstall_hook(env):
    """Turn the module's crons off and remove its scheduled jobs where it can, so Odoo removes their crons.

    A job's cron cannot leave while the job exists, and a job cannot leave while it has runs. Each finished run carries
    the audit entry of its end, which only the cleanup job removes, so a job with such a run stays, its cron off."""
    jobs = env[MODEL_SCHEDULED_JOB].sudo().search([("key", "=like", f"{JOB_KEY_PREFIX}%")])
    jobs.cron_id.active = False
    jobs.item_ids.unlink()
    env[MODEL_JOB_RUN].sudo().search(
        [("job_id", "in", jobs.ids), ("audit_entry_ids", "=", False), ("archive_file_ids", "=", False)]
    ).unlink()
    jobs.filtered(lambda job: not job.run_ids).unlink()
