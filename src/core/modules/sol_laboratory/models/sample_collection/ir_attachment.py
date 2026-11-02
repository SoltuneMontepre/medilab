from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_attachment as IrAttachmentBase
else:
    IrAttachmentBase = object


# Tệp Đính Kèm
class IrAttachment(models.Model, IrAttachmentBase):
    _name = MODEL_IR_ATTACHMENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_IR_ATTACHMENT]
    # Where Odoo stores the file and the text it extracts from it, which say nothing the checksum does not.
    _audit_exclude = ("store_fname", "index_content")

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        # Photos of a sample are shown wherever the customer's name for the sample is shown.
        reader = self.env.ref(TEST_REQUEST_READER_GROUP).id
        if self.env.su or self.env.is_system() or reader in self.env.user._get_group_ids():
            return domain
        return domain & Domain("res_model", "!=", MODEL_SAMPLE)

    def _audit_scope(self):
        # Only the files of audited documents are recorded, not Odoo's own files, such as web assets or the stored
        # values of image fields.
        files = self.sudo().filtered(
            lambda file: bool(
                file.res_id
                and not file.res_field
                and file.res_model in self.env
                and self._audit_is_audited(file.res_model)
            )
        )
        return self.browse(files.ids)

    def _audit_parents(self):
        # A file's entries name the document it is attached to.
        return {file.id: (file.res_model, file.res_id) for file in self.sudo() if file.res_model and file.res_id}

    def write(self, vals):
        self._check_document_lock()
        return super().write(vals)

    def unlink(self):
        self._check_document_lock()
        return super().unlink()

    def _check_document_lock(self):
        """Refuse changing the files of a signed or issued document, such as its PDF; documents that lock their files
        say so with _files_locked()."""
        if self.env.su:
            return
        for model_name, attachments in self.sudo().grouped("res_model").items():
            if model_name not in self.env or not hasattr(self.env[model_name], "_files_locked"):
                continue
            if self.env[model_name].sudo().browse(attachments.mapped("res_id")).exists()._files_locked():
                raise UserError(self.env._("The files of a signed or issued document cannot be changed."))
