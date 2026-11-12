from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# The accountant reads every order to invoice it, adjusts posted invoices and reconciles each day's PayOS transactions.
PERMISSIONS = (
    "sol_commerce.permission_order_read_all",
    "sol_commerce.permission_order_sample_read_all",
    "sol_commerce.permission_invoice_adjustment_read_all",
    "sol_commerce.permission_invoice_adjustment_create_all",
    "sol_commerce.permission_invoice_adjustment_edit_all",
    "sol_commerce.permission_invoice_adjustment_delete_all",
    "sol_commerce.permission_reconciliation_day_read_all",
    "sol_commerce.permission_reconciliation_day_create_all",
    "sol_commerce.permission_reconciliation_day_edit_all",
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    role = reference_as(env[MODEL_ROLE], "sol_demo.demo_role_accountant", raise_if_not_found=False)
    if role:
        role.permission_ids = [Command.link(persisted_id(env.ref(xml_id))) for xml_id in PERMISSIONS]
