from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHATTER_MIXIN, MODEL_MAIL_THREAD

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_chatter_mixin as ChatterMixinBase
else:
    ChatterMixinBase = object


# Trao Đổi: the chatter of a document, where everyone who can read it reads and posts the messages and notes people
# write. Creating the document logs nothing and follows nobody, so the chatter holds only what people wrote.
class ChatterMixin(models.AbstractModel, ChatterMixinBase):
    _name = MODEL_CHATTER_MIXIN
    _inherit = [MODEL_MAIL_THREAD]
    _description = "Chatter of a Document"
    _mail_post_access = "read"

    @api.model_create_multi
    def create(self, vals_list):
        return super(ChatterMixin, self.with_context(mail_create_nolog=True, mail_create_nosubscribe=True)).create(
            vals_list
        )
