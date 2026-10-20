from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_REPORT
from odoo.addons.sol_laboratory.constants.signing import UNSIGNED_PRINT_CONTEXT


# Báo Cáo In: a fully signed document prints as its digitally signed PDF.
class IrActionsReport(models.Model):
    _inherit = MODEL_IR_ACTIONS_REPORT

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        documents = self._digitally_signed_documents(report_ref, res_ids)
        if not documents:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if len(documents) > 1:
            raise UserError(self.env._("Print digitally signed documents one at a time."))
        documents.check_access("read")
        return documents._digital_signed_pdf(), "pdf"

    def _digitally_signed_documents(self, report_ref, res_ids):
        """The documents printed with the report their type has Viettel Sign sign, when one of them is fully signed and
        digital signing is on; nothing when the report prints as it is."""
        if not res_ids or self.env.context.get(UNSIGNED_PRINT_CONTEXT):
            return None
        report = self._get_report(report_ref)
        documents = self.env[report.model].browse([res_ids] if isinstance(res_ids, int) else res_ids)
        xml_id = getattr(documents, "_digital_signing_report", None)
        if not xml_id or self.env.ref(xml_id, raise_if_not_found=False) != report:
            return None
        if not documents._digital_signing_enabled() or all(document._digital_signing_draft() for document in documents):
            return None
        return documents
