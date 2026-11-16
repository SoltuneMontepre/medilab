from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_THREAD, MODEL_TASK

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskChatterBase
else:
    TaskChatterBase = object


# Nhiệm Vụ: its chatter, where everyone who can read it reads and posts messages and notes.
class TaskChatter(models.Model, TaskChatterBase):
    _name = MODEL_TASK
    _inherit = [MODEL_TASK, MODEL_MAIL_THREAD]
    _mail_post_access = "read"
