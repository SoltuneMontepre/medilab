from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools.misc import format_datetime

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskCollectionTravelBase
else:
    TaskCollectionTravelBase = object

# Statuses of a collection its staff member still has to make.
UPCOMING_STATUSES = ("assigned", "in_progress")


# Nhiệm Vụ: a staff member takes a sample collection only when the travel buffer is free around their other ones.
class TaskCollectionTravel(models.Model, TaskCollectionTravelBase):
    _inherit = MODEL_TASK

    @api.constrains("assignee_id", "planned_start", "planned_end", "status")
    def _check_collection_travel(self):
        collections = self.sudo().filtered(
            lambda task: bool(
                task.type_id.code == SAMPLE_COLLECTION_CODE
                and task.assignee_id
                and task.planned_start
                and task.status in UPCOMING_STATUSES
            )
        )
        if not collections:
            return
        buffer = timedelta(minutes=self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("collection_travel_minutes"))
        for task in collections:
            start = task.planned_start
            if not start:
                continue
            end = task.planned_end or start
            # Another collection clashes when it starts before this one ends and ends after it starts, both widened by
            # the buffer; one without an end ends when it starts.
            ends_after = Domain("planned_end", ">", start - buffer) | (
                Domain("planned_end", "=", False) & Domain("planned_start", ">", start - buffer)
            )
            clash = self.sudo().search(
                Domain("id", "!=", task.id)
                & Domain("type_id", "=", task.type_id.id)
                & Domain("assignee_id", "=", task.assignee_id.id)
                & Domain("status", "in", UPCOMING_STATUSES)
                & Domain("planned_start", "<", end + buffer)
                & ends_after,
                order="planned_start",
                limit=1,
            )
            if clash:
                raise ValidationError(
                    self.env._(
                        "%(person)s already collects %(other)s at %(time)s, too close to %(task)s to travel between "
                        "them.",
                        person=task.assignee_id.name,
                        other=clash.name,
                        time=format_datetime(self.env, clash.planned_start, dt_format="short"),
                        task=task.name,
                    )
                )
