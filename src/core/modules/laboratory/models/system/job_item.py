from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.laboratory.constants.models import MODEL_JOB_ITEM, MODEL_PERMISSION_MIXIN, MODEL_SCHEDULED_JOB


# Mục Tác Vụ
class JobItem(models.Model):
    _name = MODEL_JOB_ITEM
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Job Item"
    _order = "next_attempt_at, id"
    # Items are queued by features; administrators retry or cancel them.
    _permission_actions = ("read", "edit")

    # The job the item is queued for.
    job_id = fields.Many2one(MODEL_SCHEDULED_JOB, required=True, ondelete="restrict", index=True)
    # Key of the work within the job, such as delivery:812.
    item_key = fields.Char(required=True)
    # Technical name of the document the work is about.
    document_model = fields.Char()
    # Id of the document the work is about.
    document_id = fields.Integer()
    # Data the job needs to do the work.
    payload = fields.Json()
    # pending, running, done, failed or cancelled.
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="pending",
        index=True,
    )
    # When a run took the item; a running item claimed longer ago than the job's claim timeout goes back to pending.
    claimed_at = fields.Datetime()
    # Attempts made so far.
    attempts = fields.Integer(default=0)
    # Earliest time the item is tried again.
    next_attempt_at = fields.Datetime(required=True, default=fields.Datetime.now)
    # Error of the last failed attempt.
    last_error = fields.Text()
    # When the item was done.
    done_at = fields.Datetime()

    _key_unique = models.Constraint("UNIQUE(job_id, item_key)", "This work is already queued for the job.")
    _due_index = models.Index("(job_id, next_attempt_at) WHERE status IN ('pending', 'running')")

    def _compute_display_name(self):
        for item in self:
            item.display_name = f"{item.job_id.name}: {item.item_key}"

    def _document(self):
        self.ensure_one()
        return self.env[self.document_model].browse(self.document_id) if self.document_model else None

    def action_retry(self):
        if any(item.status != "failed" for item in self):
            raise UserError(self.env._("Only a failed item can be retried."))
        self.write({"status": "pending", "claimed_at": False, "next_attempt_at": fields.Datetime.now()})

    def action_cancel(self):
        if any(item.status not in ("pending", "failed") for item in self):
            raise UserError(self.env._("Only a pending or failed item can be cancelled."))
        self.write({"status": "cancelled", "claimed_at": False})

    def _succeed(self, now):
        self.write({"status": "done", "claimed_at": False, "done_at": now})

    def _defer(self, until):
        self.write({"status": "pending", "claimed_at": False, "next_attempt_at": until})

    def _fail(self, message):
        self.write({"status": "failed", "claimed_at": False, "attempts": self.attempts + 1, "last_error": message})

    def _record_failure(self, job, message, now):
        """Count an attempt: fail the item at the job's limit, else queue it again with a delay that doubles."""
        attempts = self.attempts + 1
        if attempts >= job.max_attempts:
            self.write({"status": "failed", "claimed_at": False, "attempts": attempts, "last_error": message})
            job._notify_failed_item(self)
            return f"failed after {attempts} attempts"
        next_attempt_at = now + timedelta(minutes=job.retry_delay_minutes * 2 ** (attempts - 1))
        self.write(
            {
                "status": "pending",
                "claimed_at": False,
                "attempts": attempts,
                "last_error": message,
                "next_attempt_at": next_attempt_at,
            }
        )
        return f"attempt {attempts} failed, retry at {next_attempt_at:%Y-%m-%d %H:%M}"
