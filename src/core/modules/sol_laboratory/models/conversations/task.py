from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHATTER_MIXIN, MODEL_TASK

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskChatterBase
else:
    TaskChatterBase = object


# Nhiệm Vụ: its chatter.
class TaskChatter(models.Model, TaskChatterBase):
    _name = MODEL_TASK
    _inherit = [MODEL_TASK, MODEL_CHATTER_MIXIN]
