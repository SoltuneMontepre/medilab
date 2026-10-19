from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.fields import Command
from odoo.sql_db import Cursor
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from .jobs_case import JOB_LOGGER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_JOB_ITEM,
    MODEL_PARAMETER_METHOD,
    MODEL_SCHEDULED_JOB,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.models.system.accreditation_scheduled_job import (
    ACCREDITATION_REFRESH_JOB,
    DISCOVERY_DONE,
    DISCOVERY_PARAM_PREFIX,
)


@tagged("post_install", "-at_install")
class TestAccreditationJob(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job = cls.env.ref("sol_laboratory.scheduled_job_accreditation_refresh")
        cls.Certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE]
        cls.today = cls.Certificate._laboratory_today()
        cls.certificate = cls.Certificate.create(
            {
                "code": "VILAS-JOB",
                "valid_until": cls.today,
                "method_ids": [Command.set(cls.method.ids)],
            }
        )

    def setUp(self):
        super().setUp()
        # Each test starts discovery for today from the beginning.
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )

    def run_job(self):
        with self.registry_test_mode():
            self.job.cron_id.method_direct_trigger()
        self.env.invalidate_all()

    def run_one_batch(self):
        """One SH-09 batch without the cron loop that drains the queue."""
        with self.registry_test_mode():
            self.job._run_batch()
        self.env.invalidate_all()

    def _today_pair_key(self, pair):
        return f"date:{self.today.isoformat()}:pair:{pair.id}"

    def test_daily_idempotence(self):
        self.run_job()
        first = self.env[MODEL_JOB_ITEM].search(
            [("job_id", "=", self.job.id), ("item_key", "=", self._today_pair_key(self.pair))]
        )
        self.assertEqual(first.status, "done")
        self.run_job()
        items = self.env[MODEL_JOB_ITEM].search(
            [("job_id", "=", self.job.id), ("item_key", "=", self._today_pair_key(self.pair))]
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items.status, "done")

    def test_day_after_expiry_clears_accreditation(self):
        self.assertTrue(self.pair.is_accredited)
        after = self.today + timedelta(days=1)
        with freeze_time(f"{after.isoformat()} 08:00:00"):
            self.run_job()
            self.assertFalse(self.pair.is_accredited)

    def test_missed_day_recovers_on_next_run(self):
        yesterday = self.today - timedelta(days=1)
        self.env[MODEL_SCHEDULED_JOB].queue(
            ACCREDITATION_REFRESH_JOB, f"date:{yesterday.isoformat()}:pair:{self.pair.id}"
        ).write({"status": "failed", "attempts": 3, "last_error": "missed"})
        self.certificate.valid_until = self.today - timedelta(days=1)
        self.env.cr.execute(
            "UPDATE medilab_parameter_method SET is_accredited = TRUE WHERE id = %s", [self.pair.id]
        )
        self.pair.invalidate_recordset(["is_accredited"])
        self.run_job()
        self.assertFalse(self.pair.is_accredited)

    def test_stale_true_cleared_when_no_certificates(self):
        self.certificate.unlink()
        self.env.cr.execute(
            "UPDATE medilab_parameter_method SET is_accredited = TRUE WHERE id = %s", [self.pair.id]
        )
        self.pair.invalidate_recordset(["is_accredited"])
        self.run_job()
        self.assertFalse(self.pair.is_accredited)

    def test_failed_job_retries(self):
        def fail(job, item):
            raise ValueError("refresh failed")

        with freeze_time(f"{self.today.isoformat()} 08:00:00"):
            item = self.env[MODEL_SCHEDULED_JOB].queue(
                ACCREDITATION_REFRESH_JOB, self._today_pair_key(self.pair)
            )
            with (
                patch.object(type(self.env[MODEL_SCHEDULED_JOB]), "_handle_accreditation_refresh", fail),
                mute_logger(JOB_LOGGER),
            ):
                self.run_job()
            self.assertEqual(item.status, "pending")
            self.assertEqual(item.attempts, 1)
            self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)

        # A later pass retries the item once its delay has passed, although discovery is already done.
        with freeze_time(f"{self.today.isoformat()} 08:10:00"):
            self.run_job()
            self.assertEqual(item.status, "done")
            self.assertEqual(item.attempts, 1)
            self.assertTrue(self.pair.is_accredited)

    def test_yesterday_item_does_not_apply_to_today(self):
        yesterday = self.today - timedelta(days=1)
        item = self.env[MODEL_SCHEDULED_JOB].queue(
            ACCREDITATION_REFRESH_JOB, f"date:{yesterday.isoformat()}:pair:{self.pair.id}"
        )
        item.status = "pending"
        self.certificate.valid_until = self.today
        self.assertTrue(self.pair.is_accredited)
        self.env[MODEL_SCHEDULED_JOB].browse(self.job.id)._handle_accreditation_refresh(item)
        self.assertTrue(self.pair.is_accredited)
        self.assertTrue(item.item_key.startswith(f"date:{yesterday.isoformat()}"))

    def _discovery_marker(self):
        return self.env["ir.config_parameter"].sudo().get_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}"
        )

    def test_discovery_advances_cursor_across_batches(self):
        """Each batch discovers the next ID page; it must not restart from id 0."""
        self.job.batch_size = 2
        methods = self.env[MODEL_TESTING_METHOD]
        created_pairs = self.env[MODEL_PARAMETER_METHOD]
        for index in range(6):
            method = methods.create(
                {
                    "code": f"CURSOR-{index}",
                    "name": f"Cursor {index}",
                    "field_id": self.testing_field.id,
                }
            )
            pair = self.env[MODEL_PARAMETER_METHOD].create(
                {
                    "parameter_id": self.parameter.id,
                    "method_id": method.id,
                    "unit_id": self.unit.id,
                    "department_id": self.department.id,
                }
            )
            created_pairs |= pair
            self.certificate.write({"method_ids": [Command.link(method.id)]})

        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.run_one_batch()
        first_marker = self._discovery_marker()
        self.assertNotEqual(first_marker, "0")
        self.assertNotEqual(first_marker, DISCOVERY_DONE)
        first_after = int(first_marker)
        self.assertGreater(first_after, 0)

        self.run_one_batch()
        second_marker = self._discovery_marker()
        if second_marker != DISCOVERY_DONE:
            self.assertGreater(int(second_marker), first_after)

        # Cursor must never jump back to the start mid-day.
        self.assertNotEqual(second_marker, "0")

    def test_catalog_larger_than_batch_resumes(self):
        # Shrink the batch so one cron tick cannot finish discovery or the queue.
        self.job.batch_size = 2
        methods = self.env[MODEL_TESTING_METHOD]
        for index in range(5):
            method = methods.create(
                {
                    "code": f"BATCH-{index}",
                    "name": f"Batch {index}",
                    "field_id": self.testing_field.id,
                }
            )
            self.env[MODEL_PARAMETER_METHOD].create(
                {
                    "parameter_id": self.parameter.id,
                    "method_id": method.id,
                    "unit_id": self.unit.id,
                    "department_id": self.department.id,
                }
            )
            self.certificate.write({"method_ids": [Command.link(method.id)]})

        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        queue_calls = {"n": 0}
        real_queue = type(self.env[MODEL_SCHEDULED_JOB]).queue

        def counting_queue(job, key, item_key, document=None, payload=None):
            queue_calls["n"] += 1
            return real_queue(job, key, item_key, document=document, payload=payload)

        with patch.object(type(self.env[MODEL_SCHEDULED_JOB]), "queue", counting_queue):
            self.run_one_batch()
            first_pass_queues = queue_calls["n"]
            # One discovery page only: at most batch_size new pair keys (plus none for already queued).
            self.assertLessEqual(first_pass_queues, self.job.batch_size)

            for _ in range(30):
                if self._discovery_marker() == DISCOVERY_DONE:
                    today_items = self.env[MODEL_JOB_ITEM].search(
                        [
                            ("job_id", "=", self.job.id),
                            ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
                        ]
                    )
                    if today_items and all(item.status == "done" for item in today_items):
                        break
                self.run_one_batch()

        today_items = self.env[MODEL_JOB_ITEM].search(
            [
                ("job_id", "=", self.job.id),
                ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
            ]
        )
        self.assertGreater(len(today_items), self.job.batch_size)
        self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)
        self.assertTrue(all(item.status == "done" for item in today_items))
        # Full-catalog rescans would queue about O(N^2/B) times; paged discovery stays near O(N).
        self.assertLessEqual(queue_calls["n"], len(today_items) * 2)

    def test_membership_change_during_reconciliation(self):
        self.job.batch_size = 1
        other = self.env[MODEL_TESTING_METHOD].create(
            {
                "code": "DURING-1",
                "name": "During",
                "field_id": self.testing_field.id,
            }
        )
        other_pair = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": other.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
            }
        )
        self.certificate.write({"method_ids": [Command.link(other.id)]})
        self.assertTrue(other_pair.is_accredited)

        # Queue today's work, then unlink the method before the handler runs for that pair.
        self.env[MODEL_SCHEDULED_JOB].browse(self.job.id)._discover_accreditation_refresh_all()
        self.certificate.write({"method_ids": [Command.unlink(other.id)]})
        self.assertFalse(other_pair.is_accredited)

        self.run_job()
        other_pair.invalidate_recordset(["is_accredited"])
        self.assertFalse(other_pair.is_accredited)

    def _create_scoped_pairs(self, count, code_prefix):
        pairs = self.env[MODEL_PARAMETER_METHOD]
        for index in range(count):
            method = self.env[MODEL_TESTING_METHOD].create(
                {
                    "code": f"{code_prefix}-{index}",
                    "name": f"{code_prefix} {index}",
                    "field_id": self.testing_field.id,
                }
            )
            pair = self.env[MODEL_PARAMETER_METHOD].create(
                {
                    "parameter_id": self.parameter.id,
                    "method_id": method.id,
                    "unit_id": self.unit.id,
                    "department_id": self.department.id,
                }
            )
            pairs |= pair
            self.certificate.write({"method_ids": [Command.link(method.id)]})
        return pairs

    def test_cron_drains_catalog_larger_than_batch(self):
        """method_direct_trigger finishes every discovery page without a manual _run_batch loop."""
        self.job.batch_size = 2
        pairs = self._create_scoped_pairs(7, "CRON")
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 1)
        self.run_job()
        self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 0)
        today_items = self.env[MODEL_JOB_ITEM].search(
            [
                ("job_id", "=", self.job.id),
                ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
            ]
        )
        for pair in pairs:
            item = today_items.filtered(lambda row, pair=pair: row.item_key == self._today_pair_key(pair))
            self.assertEqual(len(item), 1)
            self.assertEqual(item.status, "done")

    def test_remaining_work_while_discovery_incomplete(self):
        """After the last item of a page is done, _due_count stays positive until discovery is DONE."""
        self.job.batch_size = 2
        self._create_scoped_pairs(5, "REMAIN")
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.run_one_batch()
        self.assertNotEqual(self._discovery_marker(), DISCOVERY_DONE)

        pending = True
        while pending:
            with self.registry_test_mode():
                with patch.object(
                    type(self.env[MODEL_SCHEDULED_JOB]),
                    "_discover_accreditation_refresh_page",
                    return_value=None,
                ):
                    self.job._run_batch()
            self.env.invalidate_all()
            pending = bool(
                self.env[MODEL_JOB_ITEM].search_count(
                    [
                        ("job_id", "=", self.job.id),
                        ("status", "=", "pending"),
                        ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
                    ]
                )
            )

        self.assertNotEqual(self._discovery_marker(), DISCOVERY_DONE)
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 1)
        self.run_job()
        self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 0)

    def test_due_count_does_not_scan_remaining_catalog(self):
        """Mid-discovery, _due_count reads only today's marker, never the undiscovered pairs."""
        self.job.batch_size = 2
        self._create_scoped_pairs(12, "NOCOUNT")
        self.run_one_batch()
        self.assertNotIn(self._discovery_marker(), ("0", DISCOVERY_DONE))

        now = fields.Datetime.now()
        due_items = self.env[MODEL_JOB_ITEM].search_count(
            [("job_id", "=", self.job.id), ("status", "=", "pending"), ("next_attempt_at", "<=", now)]
        )
        queries = []
        real_execute = Cursor.execute

        def recording_execute(cr, query, params=None, log_exceptions=None):
            queries.append(str(query))
            return real_execute(cr, query, params, log_exceptions)

        self.env.flush_all()
        with patch.object(Cursor, "execute", recording_execute):
            remaining = self.job._due_count(now)
        self.assertEqual(remaining, due_items + 1)
        self.assertEqual([query for query in queries if "medilab_parameter_method" in query], [])

    def test_empty_catalog_marks_discovery_done(self):
        self.certificate.unlink()
        self.env.cr.execute(
            "UPDATE medilab_parameter_method SET is_accredited = FALSE WHERE is_accredited IS TRUE"
        )
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 1)
        self.run_job()
        self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)
        self.assertEqual(self.job._due_count(fields.Datetime.now()), 0)

    def test_discovery_interruption_and_resume(self):
        self.job.batch_size = 2
        pairs = self._create_scoped_pairs(6, "RESUME")
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.run_one_batch()
        mid = self._discovery_marker()
        self.assertNotEqual(mid, DISCOVERY_DONE)
        self.assertNotEqual(mid, "0")
        self.run_job()
        self.assertEqual(self._discovery_marker(), DISCOVERY_DONE)
        today_items = self.env[MODEL_JOB_ITEM].search(
            [
                ("job_id", "=", self.job.id),
                ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
            ]
        )
        self.assertTrue(all(item.status == "done" for item in today_items))
        self.assertGreaterEqual(len(today_items), len(pairs))

    def test_day_rollover_starts_fresh_discovery(self):
        self.job.batch_size = 2
        self._create_scoped_pairs(3, "DAY")
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        self.run_one_batch()
        today_marker = self._discovery_marker()
        self.assertNotEqual(today_marker, DISCOVERY_DONE)

        tomorrow = self.today + timedelta(days=1)
        with freeze_time(f"{tomorrow.isoformat()} 08:00:00"):
            self.env["ir.config_parameter"].sudo().set_str(
                f"{DISCOVERY_PARAM_PREFIX}{tomorrow.isoformat()}", "0"
            )
            self.run_job()
            tomorrow_marker = self.env["ir.config_parameter"].sudo().get_str(
                f"{DISCOVERY_PARAM_PREFIX}{tomorrow.isoformat()}"
            )
            self.assertEqual(tomorrow_marker, DISCOVERY_DONE)
            self.assertEqual(
                self.env["ir.config_parameter"].sudo().get_str(
                    f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}"
                ),
                today_marker,
            )

    def test_discovery_uses_sql_not_certificate_scope_materialization(self):
        """Discovery pages must not load every certificate's method_ids into Python."""
        self.job.batch_size = 2
        self._create_scoped_pairs(8, "SQL")
        self.env["ir.config_parameter"].sudo().set_str(
            f"{DISCOVERY_PARAM_PREFIX}{self.today.isoformat()}", "0"
        )
        mapped_calls = {"n": 0}
        from odoo import models as odoo_models

        real_mapped = odoo_models.BaseModel.mapped

        def counting_mapped(records, path):
            if path == "method_ids" and records._name == MODEL_ACCREDITATION_CERTIFICATE:
                mapped_calls["n"] += 1
            return real_mapped(records, path)

        with patch.object(odoo_models.BaseModel, "mapped", counting_mapped):
            for _ in range(100):
                if self._discovery_marker() == DISCOVERY_DONE:
                    break
                self.job._discover_accreditation_refresh_page()
            else:
                self.fail("discovery did not reach DONE")
        self.assertEqual(mapped_calls["n"], 0)

        # Coverage through the final pair via cron (no materialization assertion here).
        self.run_job()
        pair_ids = self.job._fetch_accreditation_pair_ids_after(0, 10_000)
        self.assertTrue(pair_ids)
        today_keys = {
            item.item_key
            for item in self.env[MODEL_JOB_ITEM].search(
                [
                    ("job_id", "=", self.job.id),
                    ("item_key", "like", f"date:{self.today.isoformat()}:pair:%"),
                ]
            )
        }
        for pair_id in pair_ids:
            self.assertIn(f"date:{self.today.isoformat()}:pair:{pair_id}", today_keys)
