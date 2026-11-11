from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_CHAIN, MODEL_PERMISSION

# The permission to sign orders, which the order approval used.
SIGN_PERMISSION = "order.sign.all"


def migrate(cr, _version):
    # A confirmed order needs no approval any more: it counts from its confirmation, which Odoo stamped as its order
    # date, and its pipeline stage is confirmed whatever its approval was. Demo history backdated the order date to the
    # claim, so a confirmation never counts from before the acceptance.
    cr.execute(
        """
        UPDATE sale_order SET confirmed_at = GREATEST(date_order, accepted_at)
         WHERE confirmed_at IS NULL AND (test_request_id IS NOT NULL OR order_status IN ('confirmed', 'completed'))
        """
    )
    cr.execute("UPDATE sale_order SET pipeline_stage = 'confirmed' WHERE order_status = 'confirmed'")
    # Odoo leaves the table of a removed model behind: the wizard that rejected the approval.
    cr.execute("DROP TABLE IF EXISTS medilab_order_reject")
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Signatures already given stay on record, so the chain that took them is archived rather than deleted.
    env[MODEL_APPROVAL_CHAIN].search(
        [("document_model", "=", MODEL_SALE_ORDER), ("purpose", "=", PURPOSE_SIGNING)]
    ).action_archive()
    # A shipped permission is deleted only the way uninstalling deletes it, with its group and access.
    env[MODEL_PERMISSION].with_context(**{MODULE_UNINSTALL_FLAG: True}).search(
        [("code", "=", SIGN_PERMISSION)]
    ).unlink()
