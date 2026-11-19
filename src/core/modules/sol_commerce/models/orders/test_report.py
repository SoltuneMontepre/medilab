from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.notifications import EVENT_RESULT_RELEASED
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report as TestReportBase
else:
    TestReportBase = object


# Phiếu Kết Quả: the results of an order are released on the order, to its contact, through the channels they chose.
class TestReport(models.Model, TestReportBase):
    _inherit = MODEL_TEST_REPORT

    def _issued_notice(self):
        order = self.request_id._sale_order()
        if not order:
            return super()._issued_notice()
        contact = order.partner_id
        body = self.with_context(lang=contact.lang).env._(
            "The results of order %(order)s are ready. Download report %(report)s from your portal.",
            order=order.name,
            report=self.code,
        )
        return EVENT_RESULT_RELEASED, order, contact, body
