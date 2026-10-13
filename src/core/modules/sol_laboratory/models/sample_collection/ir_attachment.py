from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP


# Tệp Đính Kèm
class IrAttachment(models.Model):
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
            lambda file: (
                file.res_id
                and not file.res_field
                and file.res_model in self.env
                and self._audit_is_audited(file.res_model)
            )
        )
        return self.browse(files.ids)

    @api.model
    def _audit_files_of(self, model, ids):
        """Ids of the files attached to the documents, including deleted files, which their create entries name."""
        files = set(self.sudo().search([("res_model", "=", model), ("res_id", "in", list(ids))]).ids)
        created = (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .search_fetch(
                Domain("document_model", "=", self._name)
                & Domain("action", "=", "create")
                & Domain("change_ids", "any", Domain("field_name", "=", "res_model") & Domain("new_value", "=", model))
                & Domain(
                    "change_ids",
                    "any",
                    Domain("field_name", "=", "res_id") & Domain("new_value", "in", [str(id_) for id_ in ids]),
                ),
                ["document_id"],
            )
        )
        return files | set(created.mapped("document_id"))
