from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@tagged("post_install", "-at_install")
class TestOrderPaidStepMigration(OrderCase):
    """Upgrading to the paid step moves the confirmed request of an order on to paid."""

    def migrate(self):
        self.env.flush_all()
        self.env.invalidate_all()
        load_script(str(MIGRATIONS / "20.0.1.11.0" / "post-migrate.py"), "order_paid_step_post").migrate(
            self.env.cr, "20.0.1.10.0"
        )
        self.env.invalidate_all()

    def test_the_confirmed_request_of_an_order_is_paid_and_others_are_left_alone(self):
        confirmed = self.make_confirmed_order().test_request_id
        draft = self.make_confirmed_order().test_request_id
        alone = self.env[MODEL_TEST_REQUEST].create({"customer_id": self.customer_record.id})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE medilab_test_request SET status = 'confirmed' WHERE id IN %s", (tuple((confirmed | alone).ids),)
        )

        self.migrate()

        self.assertEqual(confirmed.status, "paid")
        self.assertEqual(draft.status, "draft")
        self.assertEqual(alone.status, "confirmed")
        confirmed.sample_ids[:1].with_user(self.sales).sudo().action_receive(1, "good")
        self.assertEqual(confirmed.status, "sample_received")
