import logging
import traceback
from datetime import datetime, timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL, mute_logger

from odoo.addons.laboratory.constants.models import (
    MODEL_IR_CRON,
    MODEL_IR_CRON_PROGRESS,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SCHEDULED_JOB,
)

_logger = logging.getLogger(__name__)

HANDLER_PREFIX = "_handle_"
# Context keys Odoo's cron sets: the progress record of the batch, and the end time of the pass, which is the same
# for every batch of one pass.
CRON_PROGRESS_KEY = "ir_cron_progress_id"
CRON_PASS_KEY = "cron_end_time"


class PermanentJobError(Exception):
    """A failure a retry cannot fix; the item is marked failed at once."""


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _name = MODEL_SCHEDULED_JOB
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Scheduled Job"
    _order = "name"
    # Jobs come with modules: administrators change their schedule and limits, run them and retry their items.
    _permission_actions = ("read", "edit")

    # Unique key of the job, such as notifications.send or payos.poll; the handler is named after it.
    key = fields.Char(required=True)
    # Job name in each language.
    name = fields.Char(required=True, translate=True)
    # The Odoo cron that runs the job; its schedule is the job's schedule.
    cron_id = fields.Many2one(MODEL_IR_CRON, required=True, ondelete="restrict", copy=False)
    # Most items handled in one batch.
    batch_size = fields.Integer(default=100, required=True)
    # Attempts before an item is marked failed and an administrator is told.
    max_attempts = fields.Integer(default=5, required=True)
    # Minutes after which an item still running is treated as abandoned.
    claim_timeout_minutes = fields.Integer(default=30, required=True)
    # Minutes before the first retry; each later retry waits twice as long.
    retry_delay_minutes = fields.Integer(default=5, required=True)
    # Items queued for the job.
    item_ids = fields.One2many(MODEL_JOB_ITEM, "job_id", string="Items")
    # Runs of the job.
    run_ids = fields.One2many(MODEL_JOB_RUN, "job_id", string="Runs")
    # Administrator who asked for the next run by hand; cleared when that run starts.
    run_requested_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    # When the run by hand was asked for.
    run_requested_at = fields.Datetime(readonly=True, copy=False)
    # How many interval units pass between two scheduled runs; kept on the cron.
    interval_number = fields.Integer(related="cron_id.interval_number", readonly=False)
    # Unit of the interval; kept on the cron.
    interval_type = fields.Selection(related="cron_id.interval_type", readonly=False)
    # When the next scheduled run starts; kept on the cron.
    nextcall = fields.Datetime(related="cron_id.nextcall", readonly=False, string="Next Run")
    # When the last scheduled run started; kept on the cron.
    lastcall = fields.Datetime(related="cron_id.lastcall", string="Last Scheduled Run")
    # False when the schedule is off: items wait until it is on again or the job is run by hand; kept on the cron.
    cron_active = fields.Boolean(related="cron_id.active", readonly=False, string="Active")
    # The most recent run.
    last_run_id = fields.Many2one(MODEL_JOB_RUN, compute="_compute_last_run")
    # Result of the most recent run.
    last_run_status = fields.Selection(related="last_run_id.status")
    # Seconds the most recent run took.
    last_run_duration = fields.Float(related="last_run_id.duration")
    # Items waiting to be done.
    pending_count = fields.Integer(compute="_compute_counts")
    # Items that failed their last attempt.
    failed_count = fields.Integer(compute="_compute_counts")
    # Items done in the current cron batch, from Odoo's cron progress.
    progress_done = fields.Integer(compute="_compute_progress")
    # Items left for the current cron pass, from Odoo's cron progress.
    progress_remaining = fields.Integer(compute="_compute_progress")

    _key_unique = models.Constraint("UNIQUE(key)", "A job with this key already exists.")
    _cron_unique = models.Constraint("UNIQUE(cron_id)", "Each job has its own cron.")
    _limits_positive = models.Constraint(
        "CHECK(batch_size > 0 AND max_attempts > 0)", "The batch size and the attempts must be at least 1."
    )

    @api.depends("run_ids.started_at")
    def _compute_last_run(self):
        for job in self:
            job.last_run_id = job.run_ids.sorted(key=lambda run: (run.started_at, run.id), reverse=True)[:1]

    def _compute_counts(self):
        counts = {
            (job.id, status): count
            for job, status, count in self.env[MODEL_JOB_ITEM]._read_group(
                [("job_id", "in", self.ids), ("status", "in", ("pending", "failed"))], ["job_id", "status"], ["__count"]
            )
        }
        for job in self:
            job.pending_count = counts.get((job.id, "pending"), 0)
            job.failed_count = counts.get((job.id, "failed"), 0)

    def _compute_progress(self):
        progress_model = self.env[MODEL_IR_CRON_PROGRESS].sudo()
        for job in self:
            progress = progress_model.search([("cron_id", "=", job.cron_id.id)], order="id desc", limit=1)
            job.progress_done = progress.done
            job.progress_remaining = progress.remaining

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("cron_id"):
                vals["cron_id"] = self._create_cron(vals["key"], vals.get("name") or vals["key"]).id
        return super().create(vals_list)

    @api.model
    def _create_cron(self, key, name):
        return (
            self.env[MODEL_IR_CRON]
            .sudo()
            .create(
                {
                    "name": name,
                    "model_id": self.env["ir.model"]._get(self._name).id,
                    "state": "code",
                    "code": f'model._run_key("{key}")',
                    "interval_number": 1,
                    "interval_type": "days",
                }
            )
        )

    @api.model
    def _by_key(self, key):
        job = self.sudo().search([("key", "=", key)], limit=1)
        if not job:
            raise ValueError(f"No scheduled job has the key {key!r}")
        return job

    def _handler_name(self):
        return HANDLER_PREFIX + self.key.replace(".", "_")

    def _in_cron(self):
        return CRON_PROGRESS_KEY in self.env.context

    @api.model
    def queue(self, key, item_key, document=None, payload=None):
        """Queue one unit of work for the job with this key; the same item key is queued once."""
        job = self._by_key(key)
        items = self.env[MODEL_JOB_ITEM].sudo()
        domain = [("job_id", "=", job.id), ("item_key", "=", item_key)]
        item = items.search(domain, limit=1)
        if item:
            return item
        vals = {"job_id": job.id, "item_key": item_key, "payload": payload}
        if document is not None:
            vals.update(document_model=document._name, document_id=document.id)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return items.create(vals)
        except IntegrityError:
            # Another transaction queued the same work meanwhile.
            return items.search(domain, limit=1)

    def action_run(self):
        self.ensure_one()
        self._check_permission("edit")
        if not self.cron_id.active:
            raise UserError(self.env._("Turn the schedule of %s on before running it.", self.display_name))
        self.write({"run_requested_by_id": self.env.user.id, "run_requested_at": fields.Datetime.now()})
        self.cron_id.sudo()._trigger()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "message": self.env._("%s runs within a minute.", self.display_name),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    @api.model
    def _run_key(self, key):
        # Entry point of the job's cron: model._run_key("<key>").
        self._by_key(key)._run_batch()

    def _run_batch(self):
        """Do one batch of due items; under the cron, Odoo calls again while items remain."""
        self.ensure_one()
        job = self.sudo()
        now = fields.Datetime.now()
        run = job._current_run(now)
        job._release_abandoned(run, now)
        handler = getattr(job, job._handler_name(), None)
        if handler is None:
            run._finish("failed", f"No handler {job._handler_name()} is defined")
            job._progress(remaining=0)
            return run
        try:
            items = job._claim(now)
        except Exception:
            run._finish("failed", traceback.format_exc())
            _logger.exception("Job %s could not claim its items", job.key)
            job._progress(remaining=0)
            return run
        for item in items:
            job._process_item(item, handler, run)
            job._progress(processed=1)
        remaining = job._due_count(fields.Datetime.now())
        if not remaining or not job._in_cron():
            run._close(None if run.log else "No due items")
        job._progress(remaining=remaining)
        return run

    def _current_run(self, now):
        # The batches of one cron pass share one run; a run left running by another pass is closed first.
        cron_pass = str(self.env.context[CRON_PASS_KEY]) if CRON_PASS_KEY in self.env.context else False
        running = self.env[MODEL_JOB_RUN].search([("job_id", "=", self.id), ("status", "=", "running")])
        current = running.filtered(lambda run: bool(cron_pass) and run.cron_pass == cron_pass)[:1]
        (running - current)._close("Continued in a later pass")
        if current:
            return current
        run = self.env[MODEL_JOB_RUN].create(
            {
                "job_id": self.id,
                "started_at": now,
                "cron_pass": cron_pass,
                "triggered_by_id": self.run_requested_by_id.id,
            }
        )
        if self.run_requested_by_id:
            self.write({"run_requested_by_id": False, "run_requested_at": False})
        self._progress(remaining=self._due_count(now))
        return run

    def _release_abandoned(self, run, now):
        cutoff = now - timedelta(minutes=self.claim_timeout_minutes)
        abandoned = self.env[MODEL_JOB_ITEM].search(
            [("job_id", "=", self.id), ("status", "=", "running"), ("claimed_at", "<", cutoff)]
        )
        for item in abandoned:
            outcome = item._record_failure(self, "Claimed longer than the claim timeout; the worker may have crashed", now)
            run._append_log(f"{item.item_key}: abandoned claim released, {outcome}")

    def _claim(self, now):
        # The ORM cannot express SKIP LOCKED, which lets two workers claim different items without waiting.
        items = self.env[MODEL_JOB_ITEM]
        items.flush_model()
        self.env.cr.execute(
            SQL(
                """
                UPDATE %(table)s SET status = 'running', claimed_at = %(now)s
                WHERE id IN (
                    SELECT id FROM %(table)s
                    WHERE job_id = %(job)s AND status = 'pending' AND next_attempt_at <= %(now)s
                    ORDER BY next_attempt_at, id
                    LIMIT %(limit)s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id
                """,
                table=SQL.identifier(items._table),
                now=now,
                job=self.id,
                limit=self.batch_size,
            )
        )
        claimed = items.browse([row[0] for row in self.env.cr.fetchall()])
        claimed.invalidate_recordset(["status", "claimed_at"])
        return claimed.sorted(key=lambda item: (item.next_attempt_at, item.id))

    def _due_count(self, now):
        return self.env[MODEL_JOB_ITEM].search_count(
            [("job_id", "=", self.id), ("status", "=", "pending"), ("next_attempt_at", "<=", now)]
        )

    def _process_item(self, item, handler, run):
        now = fields.Datetime.now()
        try:
            with self.env.cr.savepoint():
                result = handler(item)
        except PermanentJobError as error:
            item._fail(str(error))
            self._notify_failed_item(item)
            run._count_failed()
            run._append_log(f"{item.item_key}: failed, {error}")
        except Exception as error:
            outcome = item._record_failure(self, traceback.format_exc(), now)
            run._count_failed()
            run._append_log(f"{item.item_key}: {outcome}, {type(error).__name__}: {error}")
        else:
            if isinstance(result, datetime):
                item._defer(result)
                run._append_log(f"{item.item_key}: deferred to {result:%Y-%m-%d %H:%M}")
            else:
                item._succeed(now)
                run._count_done()
                run._append_log(f"{item.item_key}: done")

    def _progress(self, processed=0, remaining=None):
        # Odoo's cron progress commits the batch so far and decides whether to call the next batch.
        if self._in_cron():
            self.env[MODEL_IR_CRON]._commit_progress(processed, remaining=remaining)

    def _notify_failed_item(self, item):
        # Until notifications exist, the failure is logged and shown on the Jobs screen.
        _logger.error("Job %s: item %s failed its last attempt: %s", self.key, item.item_key, item.last_error)
