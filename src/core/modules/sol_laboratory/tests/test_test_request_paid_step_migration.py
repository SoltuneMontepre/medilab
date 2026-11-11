from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .request_case import RequestCase

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@tagged("post_install", "-at_install")
class TestTestRequestPaidStepMigration(RequestCase):
    """Upgrading to the single lifecycle moves every confirmed test request on to paid."""

    def migrate(self):
        self.env.flush_all()
        self.env.invalidate_all()
        load_script(str(MIGRATIONS / "20.0.1.34.0" / "post-migrate.py"), "test_request_paid_step_post").migrate(
            self.env.cr, "20.0.1.33.0"
        )
        self.env.invalidate_all()

    def test_a_confirmed_request_is_paid_and_others_are_left_alone(self):
        draft = self.create_request()
        self.env.flush_all()
        self.env.cr.execute("UPDATE medilab_test_request SET status = 'confirmed' WHERE id = %s", (self.request.id,))

        self.migrate()

        self.assertEqual(self.request.status, "paid")
        self.assertEqual(draft.status, "draft")
        self.request._set_status("sample_received")
        self.assertEqual(self.request.status, "sample_received")
