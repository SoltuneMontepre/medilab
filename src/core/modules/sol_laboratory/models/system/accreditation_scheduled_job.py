from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_PARAMETER_METHOD,
    MODEL_SCHEDULED_JOB,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

ACCREDITATION_REFRESH_JOB = "accreditation.refresh"
# Progress of today's pair discovery: ir.config_parameter key suffix is the laboratory date.
DISCOVERY_PARAM_PREFIX = "sol_laboratory.accreditation_refresh.after_id."
DISCOVERY_DONE = "done"

# Eligible pairs: currently True (stale cleanup) or linked on any certificate (incl. archived).
_ELIGIBLE_PAIR_SQL = """
    FROM medilab_parameter_method pm
   WHERE pm.id > %(after_id)s
     AND (
          pm.is_accredited IS TRUE
          OR EXISTS (
              SELECT 1
                FROM medilab_accreditation_certificate_method_rel rel
               WHERE rel.method_id = pm.method_id
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
        # Cron only needs unfinished vs DONE; an exact remaining pair count is unnecessary.
        return 0 if self._accreditation_discovery_marker() == DISCOVERY_DONE else 1

    def _fetch_accreditation_pair_ids_after(self, after_id, limit):
        """Next ID-ordered page of eligible pairs without loading certificate scopes in Python."""
        self.env.cr.execute(
            f"""
            SELECT pm.id
            {_ELIGIBLE_PAIR_SQL}
            ORDER BY pm.id
            LIMIT %(limit)s
            """,
            {"after_id": after_id, "limit": limit},
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _discover_accreditation_refresh_page(self):
        """Enqueue the next ID-ordered page of pairs for today; do not rescan from the start."""
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        date_prefix = f"date:{today.isoformat()}"
        param_key = self._accreditation_discovery_param_key(today)
        icp = self.env[MODEL_IR_CONFIG_PARAMETER].sudo()
        marker = icp.get_str(param_key)
        if marker == DISCOVERY_DONE:
            return

        after_id = int(marker or 0)
        pair_ids = self._fetch_accreditation_pair_ids_after(after_id, self.batch_size)
        pairs = self.env[MODEL_PARAMETER_METHOD].browse(pair_ids)
        for pair in pairs:
            self.queue(
                ACCREDITATION_REFRESH_JOB,
                f"{date_prefix}:pair:{pair.id}",
                document=pair,
            )
        if not pair_ids:
            icp.set_str(param_key, DISCOVERY_DONE)
            return
        icp.set_str(param_key, str(pair_ids[-1]))

    def _handle_accreditation_refresh(self, item):
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        expected_prefix = f"date:{today.isoformat()}:pair:"
        # A failed or leftover item for another day must not apply yesterday's state to today.
        if not item.item_key.startswith(expected_prefix):
            return
        try:
            pair_id = int(item.item_key[len(expected_prefix) :])
        except ValueError:
            return
        pair = self.env[MODEL_PARAMETER_METHOD].with_context(active_test=False).browse(pair_id).exists()
        if pair:
            pair._recompute_is_accredited()
