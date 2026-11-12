from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_FILE, MODEL_AUDIT_ENTRY

# Records 20.0.1.3.0 shipped without updates, which Odoo leaves behind when a version no longer ships them. Stock items
# in the category are left without one, as this version makes them.
LEFTOVER_RECORDS = (
    "sol_inventory.product_category_stock_item",
    "sol_inventory.scrap_reason_contaminated",
    "sol_inventory.scrap_reason_dropped",
    "sol_inventory.scrap_reason_expired",
    "sol_inventory.scrap_reason_other",
    "sol_inventory.scrap_reason_spilled",
    "sol_inventory.scrap_reason_wrongly_prepared",
    "sol_inventory.sequence_preparation_lot",
)
# Shipped permissions of the same version.
LEFTOVER_PERMISSIONS = (
    "sol_inventory.permission_container_edit_all",
    "sol_inventory.permission_move_create_all",
    "sol_inventory.permission_move_read_all",
    "sol_inventory.permission_preparation_create_all",
    "sol_inventory.permission_stock_read_all",
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _delete_stock_expiry_job(env)
    for xmlid in LEFTOVER_PERMISSIONS:
        permission = env.ref(xmlid, raise_if_not_found=False)
        if permission:
            # A shipped permission is deleted only the way uninstalling deletes it, with its group and access.
            permission.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
    for xmlid in LEFTOVER_RECORDS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.unlink()
    env.flush_all()
    # Odoo deletes the models 20.0.1.3.0 had and this version does not, but leaves their tables and rows behind. Their
    # foreign keys would also keep the recipes, locations and containers they name from being deleted.
    cr.execute(
        """
        DROP TABLE IF EXISTS
            medilab_container_opening,
            medilab_container_scan,
            medilab_preparation,
            medilab_preparation_make,
            medilab_preparation_make_container,
            medilab_preparation_make_line,
            medilab_preparation_make_stock_scrap_reason_tag_rel,
            medilab_result_container,
            medilab_stock_correction,
            medilab_stock_relocation,
            medilab_stock_use,
            medilab_stock_use_stock_scrap_reason_tag_rel
        CASCADE
        """
    )
    # A container's item and lot are computed again; Odoo keeps the columns that stored them.
    cr.execute("ALTER TABLE stock_package DROP COLUMN IF EXISTS item_id, DROP COLUMN IF EXISTS lot_id")


def _delete_stock_expiry_job(env):
    # The job has no handler in this version. The audit trail is never deleted, so runs it or an archive file names
    # keep the job; its schedule is turned off instead.
    job = env.ref("sol_inventory.scheduled_job_stock_expiry", raise_if_not_found=False)
    cron = env.ref("sol_inventory.ir_cron_stock_expiry", raise_if_not_found=False)
    if job:
        job.item_ids.unlink()
        named = env[MODEL_AUDIT_ENTRY].search([("job_run_id", "in", job.run_ids.ids)]).job_run_id
        named |= env[MODEL_ARCHIVE_FILE].search([("job_run_id", "in", job.run_ids.ids)]).job_run_id
        (job.run_ids - named).unlink()
        if named:
            job.cron_id.active = False
            return
        job.unlink()
    if cron:
        # Deleting a cron leaves the server action it is made from.
        action = cron.ir_actions_server_id
        cron.unlink()
        action.unlink()
