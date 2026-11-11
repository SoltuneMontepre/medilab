from datetime import timedelta

from odoo import fields

from .demo_orders import _xml_id
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TASK_REMINDER

# The task reminders in demo.tester's inbox, by the end of their xml id: the task, whether it is read and how many hours
# ago it was sent. The lead task of the running sample went to another tester, so demo.tester can no longer open it.
REMINDERS = (
    ("balance_check", "demo_task_balance_check", False, 1),
    ("lead_running", "demo_task_sample_test_lead_running", False, 3),
    ("waste_log", "demo_task_waste_log", True, 26),
)


def seed_notifications(env):
    """demo.tester's inbox on the web and Medilab Mobile: task reminders read and unread, one of them about a task the
    tester can no longer see. Posted as the reminder job posts them, without queuing an email or a push."""
    messages = env[MODEL_MAIL_MESSAGE].sudo()
    tester = env.ref("sol_demo.demo_res_users_tester")
    event = env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_TASK_REMINDER)
    for name, task_xml_id, read, hours in REMINDERS:
        key = f"demo:{name}:reminder"
        if messages.search_count([("notification_key", "=", key)], limit=1):
            continue
        task = env.ref(f"sol_demo.{task_xml_id}")
        message = messages.create(
            {
                "model": task._name,
                "res_id": task.id,
                "body": "Starts in 15 minutes.",
                "subject": task.name,
                "message_type": "notification",
                "subtype_id": event.id,
                "notification_key": key,
                "date": fields.Datetime.now() - timedelta(hours=hours),
            }
        )
        env[MODEL_MAIL_NOTIFICATION].sudo().create(
            {
                "mail_message_id": message.id,
                "res_partner_id": tester.partner_id.id,
                "notification_type": "inbox",
                "notification_status": "sent",
                "is_read": read,
            }
        )
        _xml_id(env, f"demo_mail_message_{name}_reminder", message)
