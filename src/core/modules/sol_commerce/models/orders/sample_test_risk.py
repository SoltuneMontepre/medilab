from typing import TYPE_CHECKING

from odoo import models
from odoo.tools.misc import format_date

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST
from odoo.addons.sol_laboratory.services.staff_language import staff_env

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestRiskBase
else:
    SampleTestRiskBase = object


# Chỉ Tiêu Của Mẫu: the salesperson of the order hears when one of its tests may miss the date promised to the customer,
# so they can agree a feasible date with the customer.
class SampleTestRisk(models.Model, SampleTestRiskBase):
    _inherit = MODEL_SAMPLE_TEST

    def _flag_at_risk(self):
        new = self.sudo().filtered(lambda test: not test.at_risk)
        result = super()._flag_at_risk()
        for request in new.sample_id.request_id:
            order = request._sale_order()
            if not (order and order.user_id and request.committed_date):
                continue
            salesperson = order.user_id
            env = staff_env(self.env, salesperson)
            body = env._(
                "Some tests of order %(order)s are at risk of missing the expected return date %(date)s. Agree a "
                "feasible date with the customer if the laboratory cannot catch up.",
                order=order.name,
                date=format_date(env, request.committed_date),
            )
            order.message_post(body=body, partner_ids=salesperson.partner_id.ids, subtype_xmlid="mail.mt_comment")
        return result
