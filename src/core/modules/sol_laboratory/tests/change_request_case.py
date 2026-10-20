from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_CHANGE_REQUEST
from odoo.addons.sol_laboratory.constants.models import MODEL_CHANGE_REQUEST, MODEL_TEST_REPORT, MODEL_TEST_RESULT


class ChangeRequestCase(ReportCase):
    """The lab head approves the change requests on results, which the tester raises, and on reports, which the sample
    delivery staff member raises."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for document_model, code in (
            (MODEL_TEST_RESULT, "qa_result_changes"),
            (MODEL_TEST_REPORT, "qa_report_changes"),
        ):
            chain = cls.approval_chain(document_model, (("Lab head", code, False, True),), PURPOSE_CHANGE_REQUEST)
            cls.lab_head.role_ids |= chain.level_ids.role_id
        cls.grant(cls.lab_head, "change_request.read.all", "change_request.sign.all")
        cls.tester.user_id.notification_type = "inbox"

    def raise_on(self, document, person=None, change="Change the lead value to 0.006.", reason="The dilution was 4."):
        return (
            self.env[MODEL_CHANGE_REQUEST]
            .with_user((person or self.tester).user_id)
            ._raise(document._name, document.id, change, reason)
        )

    def messages(self, request):
        return self.env["mail.message"].search([("model", "=", request._name), ("res_id", "=", request.id)])
