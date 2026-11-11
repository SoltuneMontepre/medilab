from datetime import timedelta

from odoo import api, fields
from odoo.api import SUPERUSER_ID


def migrate(cr, _version):
    # The booking waiting in the queue is one no machine can finish by its due date, as the scheduler leaves it.
    env = api.Environment(cr, SUPERUSER_ID, {})
    booking = env.ref("sol_demo.demo_machine_booking_lead_queued", raise_if_not_found=False)
    if not booking or booking.status != "queued":
        return
    due = fields.Datetime.now() + timedelta(minutes=30)
    booking.sample_test_id.write({"due_date": due, "outsourcing_suggested": True})
    booking.task_id.write({"deadline": due})
