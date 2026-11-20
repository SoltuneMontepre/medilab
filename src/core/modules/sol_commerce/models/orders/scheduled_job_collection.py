from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools.misc import format_datetime

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB, MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.services.staff_language import staff_env

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

UNCLAIMED_COLLECTION_KEY = "collections.unclaimed"
# How long before its appointment a collection nobody claimed is raised with the salesperson who agreed it.
UNCLAIMED_COLLECTION_LEAD = timedelta(hours=24)


# Tác Vụ Định Kỳ: a sample collection still in the queue a day before its appointment is raised with the salesperson
# who agreed the appointment with the customer.
class ScheduledJobCollection(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_collections_unclaimed(self):
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        now = fields.Datetime.now()
        tasks = (
            self.env[MODEL_TASK]
            .sudo()
            .search(
                [
                    ("type_id", "=", task_type.id),
                    ("status", "=", "open"),
                    ("assignee_id", "=", False),
                    ("deadline", ">", now),
                    ("deadline", "<=", now + UNCLAIMED_COLLECTION_LEAD),
                ]
            )
        )
        for task in tasks:
            stamp = fields.Datetime.to_string(task.deadline)
            self.env[MODEL_SCHEDULED_JOB].queue(UNCLAIMED_COLLECTION_KEY, f"{task.id}:{stamp}", document=task)

    def _handle_collections_unclaimed(self, item):
        task = item._document()
        if not task or not task.exists() or task.status != "open" or task.assignee_id or not task.deadline:
            return
        order = self.env[MODEL_SALE_ORDER].sudo().search([("test_request_id", "=", task.document_id)], limit=1)
        if task.document_model != order.test_request_id._name or not order:
            return
        salesperson = order.user_id
        env = staff_env(self.env, salesperson)
        order.message_post(
            body=env._(
                "Nobody has claimed the sample collection of order %(order)s, due at %(appointment)s.",
                order=order.name,
                appointment=format_datetime(env, task.deadline, tz=salesperson.tz or self.env.company.tz),
            ),
            partner_ids=salesperson.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
