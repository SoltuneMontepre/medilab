from datetime import datetime, timedelta
from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@tagged("post_install", "-at_install")
class TestTestRequestPaidStepMigration(RequestCase):
    """Upgrading to the sales-decoupled lifecycle moves paid/on_credit requests back to confirmed and backfills task ends."""

    def migrate(self):
        self.env.flush_all()
        self.env.invalidate_all()
        load_script(str(MIGRATIONS / "20.0.1.60.0" / "pre-migrate.py"), "test_request_decouple_pre").migrate(
            self.env.cr, "20.0.1.59.0"
        )
        self.env.invalidate_all()

    def test_paid_and_credit_requests_move_to_confirmed_and_open_collections_get_an_end(self):
        draft = self.create_request()
        credit = self.create_request()
        task_type = self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        start = datetime(2026, 11, 20, 8, 0)
        task = self.env[MODEL_TASK].create(
            {
                "type_id": task_type.id,
                "name": "Collect legacy sample",
                "document_model": self.request._name,
                "document_id": self.request.id,
                "department_id": self.department.id,
                "status": "open",
                "planned_start": start,
                "deadline": start + timedelta(days=1),
            }
        )
        self.env.flush_all()
        self.env.cr.execute("UPDATE medilab_test_request SET status = 'paid' WHERE id = %s", (self.request.id,))
        self.env.cr.execute("UPDATE medilab_test_request SET status = 'on_credit' WHERE id = %s", (credit.id,))

        self.migrate()

        self.assertEqual(self.request.status, "confirmed")
        self.assertEqual(credit.status, "confirmed")
        self.assertEqual(draft.status, "draft")
        self.assertEqual(task.planned_end, start + timedelta(minutes=60))
        self.request._set_status("sample_received")
        self.assertEqual(self.request.status, "sample_received")
