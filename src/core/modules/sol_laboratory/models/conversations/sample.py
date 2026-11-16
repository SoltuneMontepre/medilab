from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_THREAD, MODEL_SAMPLE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleChatterBase
else:
    SampleChatterBase = object


# Mẫu: its chatter, where everyone who can read it reads and posts messages and notes.
class SampleChatter(models.Model, SampleChatterBase):
    _name = MODEL_SAMPLE
    _inherit = [MODEL_SAMPLE, MODEL_MAIL_THREAD]
    _mail_post_access = "read"
