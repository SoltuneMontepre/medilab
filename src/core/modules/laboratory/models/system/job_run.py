from odoo import api, fields, models

from odoo.addons.laboratory.constants.models import MODEL_JOB_RUN, MODEL_PERMISSION_MIXIN, MODEL_SCHEDULED_JOB


# Lượt Chạy Tác Vụ
class JobRun(models.Model):
    _name = MODEL_JOB_RUN
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Job Run"
    _order = "started_at desc, id desc"
    # Runs are written by the jobs themselves; administrators read them.
    _permission_actions = ("read",)

    # The job run.
    job_id = fields.Many2one(MODEL_SCHEDULED_JOB, required=True, ondelete="restrict", index=True)
    # When the run started.
    started_at = fields.Datetime(required=True)
    # When the run ended; empty while it runs.
    ended_at = fields.Datetime()
    # running, succeeded, partly_failed or failed.
    status = fields.Selection(
        [("running", "Running"), ("succeeded", "Succeeded"), ("partly_failed", "Partly Failed"), ("failed", "Failed")],
        required=True,
        default="running",
    )
    # Log of the run, one line per item.
    log = fields.Text()
    # Administrator who ran the job by hand; empty for a scheduled run.
    triggered_by_id = fields.Many2one("res.users", ondelete="restrict")
    # The cron pass the run belongs to, so the batches of one pass share one run.
    cron_pass = fields.Char()
    # Items done in the run.
    done_count = fields.Integer(default=0)
    # Items that failed an attempt in the run.
    failed_count = fields.Integer(default=0)
    # Seconds the run took so far.
    duration = fields.Float(compute="_compute_duration")

    @api.depends("started_at", "ended_at")
    def _compute_duration(self):
        now = fields.Datetime.now()
        for run in self:
            run.duration = ((run.ended_at or now) - run.started_at).total_seconds() if run.started_at else 0

    def _compute_display_name(self):
        for run in self:
            run.display_name = f"{run.job_id.name} {run.started_at:%Y-%m-%d %H:%M}" if run.started_at else run.job_id.name

    def _append_log(self, line):
        for run in self:
            run.log = f"{run.log}\n{line}" if run.log else line

    def _count_done(self):
        for run in self:
            run.done_count += 1

    def _count_failed(self):
        for run in self:
            run.failed_count += 1

    def _close(self, note=None):
        for run in self.filtered(lambda run: run.status == "running"):
            if note:
                run._append_log(note)
            if run.failed_count and not run.done_count:
                status = "failed"
            elif run.failed_count:
                status = "partly_failed"
            else:
                status = "succeeded"
            run.write({"status": status, "ended_at": fields.Datetime.now()})

    def _finish(self, status, message):
        self._append_log(message)
        self.write({"status": status, "ended_at": fields.Datetime.now()})
