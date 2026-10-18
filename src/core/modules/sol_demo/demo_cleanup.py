from datetime import timedelta

from odoo import fields
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.jobs import CLEANUP_JOB, JOB_RUN_CONTEXT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_FILE,
    MODEL_AUDIT_ENTRY,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.settings import (
    JOB_RETENTION_PARAMETER,
    NOTIFICATION_RETENTION_PARAMETER,
)

# Short periods, so the next cleanup run removes the old records below.
SHORT_RETENTION_DAYS = 30
OLD_DAYS = 60
ARCHIVED_DAYS = 400
INTEGRATION_NOTES = ("PayOS confirmed a payment", "Brevo delivered an email", "Firebase sent a push")


def seed_cleanup(env):
    """Short retention periods with old finished job items and read notifications for the next cleanup run to
    remove, and the archive file a demo cleanup run wrote of audit entries from more than a year ago."""
    if env.ref("sol_demo.demo_archive_file_audit", raise_if_not_found=False):
        return
    parameters = env["ir.config_parameter"].sudo()
    parameters.set_int(JOB_RETENTION_PARAMETER, SHORT_RETENTION_DAYS)
    parameters.set_int(NOTIFICATION_RETENTION_PARAMETER, SHORT_RETENTION_DAYS)
    job = env[MODEL_SCHEDULED_JOB]._by_key(CLEANUP_JOB)
    echo = env.ref("sol_demo.demo_scheduled_job_echo")
    items = env[MODEL_JOB_ITEM].create(
        [
            {"job_id": echo.id, "item_key": f"greeting:old:{number}", "status": "done", "attempts": 1}
            for number in range(1, 4)
        ]
    )
    _backdate(env, items, "write_date", OLD_DAYS)
    lab_head = env.ref("sol_demo.demo_res_users_lab_head")
    regulation = env.ref("sol_demo.demo_regulation_qcvn_6_1")
    message = env[MODEL_MAIL_MESSAGE].create(
        {
            "model": regulation._name,
            "res_id": regulation.id,
            "body": f"{regulation.display_name} is free to edit.",
            "message_type": "notification",
            "notification_key": "demo:cleanup:notification",
            "date": fields.Datetime.now() - timedelta(days=OLD_DAYS),
        }
    )
    env[MODEL_MAIL_NOTIFICATION].create(
        {
            "mail_message_id": message.id,
            "res_partner_id": lab_head.partner_id.id,
            "notification_type": "inbox",
            "is_read": True,
        }
    )
    entries = env[MODEL_AUDIT_ENTRY].sudo()
    archived = entries.create(
        [{**entries._origin_values(), "action": "integration", "note": note} for note in INTEGRATION_NOTES]
    )
    _backdate(env, archived, "create_date", ARCHIVED_DAYS)
    now = fields.Datetime.now()
    run = env[MODEL_JOB_RUN].create(
        {"job_id": job.id, "started_at": now, "ended_at": now, "status": "succeeded", "log": "Demo cleanup run"}
    )
    month = (fields.Date.today() - timedelta(days=ARCHIVED_DAYS)).replace(day=1)
    archive = env[MODEL_ARCHIVE_FILE].with_context(**{JOB_RUN_CONTEXT: run.id})._archive_audit_month(month)
    env["ir.model.data"]._update_xmlids(
        [{"xml_id": "sol_demo.demo_archive_file_audit", "record": archive, "noupdate": True}]
    )


def _backdate(env, records, column, days):
    # The ORM sets these columns itself, so the demo dates them back in the database.
    env.flush_all()
    env.cr.execute(
        SQL(
            "UPDATE %s SET %s = %s WHERE id IN %s",
            SQL.identifier(records._table),
            SQL.identifier(column),
            fields.Datetime.now() - timedelta(days=days),
            tuple(records.ids),
        )
    )
    records.invalidate_recordset()
