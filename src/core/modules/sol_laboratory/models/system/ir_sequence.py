from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_SEQUENCE

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_sequence as IrSequenceBase
else:
    IrSequenceBase = object


# Dãy Số
class IrSequence(models.Model, IrSequenceBase):
    _inherit = MODEL_IR_SEQUENCE

    def _create_date_range_seq(self, date):
        # A prefix with the range's month numbers again every month; Odoo's ranges last a year.
        if "%(range_month)s" not in (self.prefix or ""):
            return super()._create_date_range_seq(date)
        first_day = fields.Date.to_date(date).replace(day=1)
        return (
            self.env["ir.sequence.date_range"]
            .sudo()
            .create(
                {
                    "sequence_id": self.id,
                    "date_from": first_day,
                    "date_to": first_day + relativedelta(months=1, days=-1),
                }
            )
        )
