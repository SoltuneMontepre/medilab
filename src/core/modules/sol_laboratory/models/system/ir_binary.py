from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_IR_BINARY


# Nội Dung Tệp
class IrBinary(models.AbstractModel):
    _inherit = MODEL_IR_BINARY

    def _get_stream_from(
        self,
        record,
        field_name="raw",
        filename=None,
        filename_field="name",
        mimetype=None,
        default_mimetype="application/octet-stream",
    ):
        stream = super()._get_stream_from(record, field_name, filename, filename_field, mimetype, default_mimetype)
        # Odoo's content routes ask for a download, not a file shown in the browser, with this context.
        if record.env.context.get("download_attachments") and self.env[MODEL_AUDIT_MIXIN]._audit_is_audited(
            record._name
        ):
            record._audit_scope()._audit("download", stream.download_name)
        return stream
