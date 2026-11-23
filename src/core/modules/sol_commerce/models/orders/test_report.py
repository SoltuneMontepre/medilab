from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.notifications import EVENT_RESULT_RELEASED
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_TEST_REPORT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_report as TestReportBase
else:
    TestReportBase = object


# Phiếu Kết Quả: the results of an order are released on the order, to its contact, through the channels they chose,
# once the order is paid in full unless its customer may order on credit.
class TestReport(models.Model, TestReportBase):
    _inherit = MODEL_TEST_REPORT

    if not TYPE_CHECKING:
        # True while the report's order is not paid in full and its customer may not order on credit: the customer can
        # neither download the report nor be sent it.
        withheld_for_payment = fields.Boolean(compute="_compute_withheld_for_payment")
        # The order whose payment the report waits for.
        withheld_order_name = fields.Char(compute="_compute_withheld_for_payment")

    def _compute_withheld_for_payment(self):
        for report in self:
            order = report.sudo().request_id._sale_order()
            withheld = bool(order) and order._withholds_report()
            report.withheld_for_payment = withheld
            report.withheld_order_name = order.name if withheld else False

    def _issued_notice(self):
        order = self.request_id._sale_order()
        if not order:
            return super()._issued_notice()
        contact = order.partner_id
        env = self.with_context(lang=contact.lang).env
        if self.withheld_for_payment:
            body = env._(
                "The results of order %(order)s are ready. Report %(report)s is released in your portal once the "
                "order is paid in full.",
                order=order.name,
                report=self.code,
            )
        else:
            body = env._(
                "The results of order %(order)s are ready. Download report %(report)s from your portal.",
                order=order.name,
                report=self.code,
            )
        return EVENT_RESULT_RELEASED, order, contact, body

    def _record_delivery(self):
        for report in self.sudo().filtered("withheld_for_payment"):
            raise UserError(
                self.env._(
                    "%(report)s is sent once order %(order)s is paid in full.",
                    report=report.code,
                    order=report.withheld_order_name,
                )
            )
        return super()._record_delivery()

    @api.model
    def _portal_domain(self, user):
        domain = super()._portal_domain(user)
        customer = self.env[MODEL_CUSTOMER]._of_user(user)
        withheld = self.sudo().search(domain).filtered("withheld_for_payment") if customer else self.browse()
        return domain & Domain("id", "not in", withheld.ids) if withheld else domain
