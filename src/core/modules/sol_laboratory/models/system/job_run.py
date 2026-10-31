from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.jobs import JOB_RUN_CONTEXT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_FILE,
    MODEL_AUDIT_ENTRY,
    MODEL_JOB_RUN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SCHEDULED_JOB,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_job_run as JobRunBase
else:
    JobRunBase = object


# Lượt Chạy Tác Vụ
class JobRun(models.Model, JobRunBase):
    _name = MODEL_JOB_RUN
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Job Run"
    _order = "started_at desc, id desc"
    # Runs are written by the jobs themselves; administrators read them.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The job run.
        job_id = fields.Many2one(
            MODEL_SCHEDULED_JOB, string="Scheduled Job", required=True, ondelete="restrict", index=True
        )
        # When the run started.
        started_at = fields.Datetime(required=True)
        # When the run ended; empty while it runs.
        ended_at = fields.Datetime()
        # running, succeeded, partly_failed or failed.
        status = fields.Selection(
            [
                ("running", "Running"),
                ("succeeded", "Succeeded"),
                ("partly_failed", "Partly Failed"),
                ("failed", "Failed"),
            ],
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
        # Audit entries written by the run.
        audit_entry_ids = fields.One2many(MODEL_AUDIT_ENTRY, "job_run_id", string="Audit Entries")
        # Archive files the run wrote.
        archive_file_ids = fields.One2many(MODEL_ARCHIVE_FILE, "job_run_id", string="Archive Files")

    @api.model
    def _cleanup_domain(self, cutoff):
        """The runs the cleanup job removes: ended before the cutoff. A run that audit entries or archive files name
        stays as long as they do."""
        return [
            ("status", "!=", "running"),
            ("ended_at", "<", cutoff),
            ("audit_entry_ids", "=", False),
            ("archive_file_ids", "=", False),
        ]

    @api.depends("started_at", "ended_at")
    def _compute_duration(self):
        now = fields.Datetime.now()
        for run in self:
            run.duration = ((run.ended_at or now) - run.started_at).total_seconds() if run.started_at else 0

    def _compute_display_name(self):
        for run in self:
            run.display_name = (
                f"{run.job_id.name} {run.started_at:%Y-%m-%d %H:%M}" if run.started_at else run.job_id.name
            )

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
        running = self.filtered(lambda run: run.status == "running")
        for run in running:
            if note:
                run._append_log(note)
            if run.failed_count and not run.done_count:
                status = "failed"
            elif run.failed_count:
                status = "partly_failed"
            else:
                status = "succeeded"
            run.write({"status": status, "ended_at": fields.Datetime.now()})
        running._audit_end()

    def _finish(self, status, message):
        self._append_log(message)
        self.write({"status": status, "ended_at": fields.Datetime.now()})
        self._audit_end()

    def _audit_end(self):
        # Each run ends with a job entry on its job, linking the run.
        statuses = dict(self._fields["status"]._description_selection(self.env))
        for run in self:
            run.job_id.with_context(**{JOB_RUN_CONTEXT: run.id})._audit(
                "job",
                self.env._(
                    "%(status)s: %(done)s done, %(failed)s failed",
                    status=statuses[run.status or ""],
                    done=run.done_count,
                    failed=run.failed_count,
                ),
            )
