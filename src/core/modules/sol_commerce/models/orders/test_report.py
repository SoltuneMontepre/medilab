from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT


# Phiếu Kết Quả: the results of an order are released on the order, to its contact.
class TestReport(models.Model):
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
        return order, contact, body
