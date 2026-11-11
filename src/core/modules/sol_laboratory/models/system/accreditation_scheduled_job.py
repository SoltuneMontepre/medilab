from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_SAMPLE_TEST,
    MODEL_SCHEDULED_JOB,
    MODEL_TESTING_METHOD,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

ACCREDITATION_REFRESH_JOB = "accreditation.refresh"
# Progress of today's method discovery: ir.config_parameter key suffix is the laboratory date.
DISCOVERY_PARAM_PREFIX = "sol_laboratory.accreditation_refresh.after_id."
DISCOVERY_DONE = "done"

# Eligible methods: on a scope line of any certificate (incl. archived), or still marking an applicability or an open
# sample test accredited (stale cleanup).
_ELIGIBLE_METHOD_SQL = """
    FROM medilab_testing_method m
   WHERE m.id > %(after_id)s
     AND (
          EXISTS (SELECT 1 FROM medilab_accreditation_scope_line line WHERE line.method_id = m.id)
          OR EXISTS (
              SELECT 1
                FROM medilab_parameter_method_sample_type applicability
                JOIN medilab_parameter_method way ON way.id = applicability.parameter_method_id
               WHERE way.method_id = m.id AND applicability.is_accredited IS TRUE
          )
          OR EXISTS (
              SELECT 1
                FROM medilab_sample_test test
                JOIN medilab_parameter_method way ON way.id = test.parameter_method_id
               WHERE way.method_id = m.id AND test.is_accredited IS TRUE AND test.status <> ALL(%(finished)s)
          )
     )
"""


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        if self.key == ACCREDITATION_REFRESH_JOB:
            # One bounded discovery page, then the usual SH-09 claim/execute batch.
            self._discover_accreditation_refresh_page()
        return super()._run_batch()

    def _due_count(self, now):
        count = super()._due_count(now)
        if self.key != ACCREDITATION_REFRESH_JOB:
            return count
        # Pending discovery pages must keep the cron pass alive after the last queued item.
        return count + self._accreditation_discovery_remaining()

    def _accreditation_discovery_param_key(self, day=None):
        day = day or self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        return f"{DISCOVERY_PARAM_PREFIX}{day.isoformat()}"

    def _accreditation_discovery_marker(self, day=None):
        return self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str(self._accreditation_discovery_param_key(day))

    def _accreditation_discovery_remaining(self):
        # Cron only needs unfinished vs DONE; an exact remaining method count is unnecessary.
        return 0 if self._accreditation_discovery_marker() == DISCOVERY_DONE else 1

    def _fetch_accreditation_method_ids_after(self, after_id, limit):
        """Next ID-ordered page of eligible methods without loading certificate scopes in Python."""
        self.env.cr.execute(
            f"""
            SELECT m.id
            {_ELIGIBLE_METHOD_SQL}
            ORDER BY m.id
            LIMIT %(limit)s
            """,
            {
                "after_id": after_id,
                "limit": limit,
                "finished": list(self.env[MODEL_SAMPLE_TEST]._finished_statuses()),
            },
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _discover_accreditation_refresh_page(self):
        """Enqueue the next ID-ordered page of methods for today; do not rescan from the start."""
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        date_prefix = f"date:{today.isoformat()}"
        param_key = self._accreditation_discovery_param_key(today)
        icp = self.env[MODEL_IR_CONFIG_PARAMETER].sudo()
        marker = icp.get_str(param_key)
        if marker == DISCOVERY_DONE:
            return

        after_id = int(marker or 0)
        method_ids = self._fetch_accreditation_method_ids_after(after_id, self.batch_size)
        methods = self.env[MODEL_TESTING_METHOD].browse(method_ids)
        for method in methods:
            self.queue(
                ACCREDITATION_REFRESH_JOB,
                f"{date_prefix}:method:{method.id}",
                document=method,
            )
        if not method_ids:
            icp.set_str(param_key, DISCOVERY_DONE)
            return
        icp.set_str(param_key, str(method_ids[-1]))

    def _handle_accreditation_refresh(self, item):
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        expected_prefix = f"date:{today.isoformat()}:method:"
        # A failed or leftover item for another day must not apply yesterday's state to today.
        if not item.item_key.startswith(expected_prefix):
            return
        try:
            method_id = int(item.item_key[len(expected_prefix) :])
        except ValueError:
            return
        method = self.env[MODEL_TESTING_METHOD].with_context(active_test=False).browse(method_id)
        self.env[MODEL_ACCREDITATION_CERTIFICATE]._recompute_accreditation(method)
