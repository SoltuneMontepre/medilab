from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.modules.module import load_script
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_CHAIN, MODEL_PERMISSION

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@tagged("post_install", "-at_install")
class TestOrderApprovalMigration(OrderCase):
    """Upgrading from the order approval leaves confirmed orders counted from their confirmation."""

    def migrate(self):
        self.env.flush_all()
        load_script(str(MIGRATIONS / "20.0.1.6.0" / "post-migrate.py"), "order_approval_post").migrate(
            self.env.cr, "20.0.1.5.0"
        )
        self.env.invalidate_all()

    def test_a_confirmed_order_counts_from_its_order_date_in_the_confirmed_stage(self):
        confirmed = self.make_confirmed_order()
        draft = self.make_quotable_order()
        self.env.flush_all()
        self.env.cr.execute(
            """
            UPDATE sale_order SET confirmed_at = NULL, pipeline_stage = 'accepted', date_order = '2026-09-05 08:00:00'
             WHERE id = %s
            """,
            (confirmed.id,),
        )

        self.migrate()

        self.assertEqual(confirmed.confirmed_at, fields.Datetime.to_datetime("2026-09-05 08:00:00"))
        self.assertEqual(confirmed.pipeline_stage, "confirmed")
        self.assertFalse(draft.confirmed_at)
        self.assertEqual(draft.pipeline_stage, "draft")

    def test_the_order_signing_chain_is_archived_and_the_sign_permission_deleted(self):
        chain = self.env[MODEL_APPROVAL_CHAIN].search(
            [("document_model", "=", MODEL_SALE_ORDER), ("purpose", "=", PURPOSE_SIGNING)]
        ) or self.env[MODEL_APPROVAL_CHAIN].create(
            {"document_model": MODEL_SALE_ORDER, "purpose": PURPOSE_SIGNING, "name": "Order signing"}
        )
        permissions = self.env[MODEL_PERMISSION]
        # Orders are no longer signed, so the permission the module used to ship can only be made this way.
        with patch.object(type(permissions), "_check_action"):
            sign = permissions.create({"name": "Sign orders", "document_model": MODEL_SALE_ORDER, "action": "sign"})
        self.env["ir.model.data"].create(
            {
                "module": "sol_commerce",
                "name": "permission_order_sign_all",
                "model": MODEL_PERMISSION,
                "res_id": sign.id,
            }
        )
        group = sign.group_id

        self.migrate()

        self.assertFalse(chain.active)
        self.assertFalse(sign.exists())
        self.assertFalse(group.exists())
