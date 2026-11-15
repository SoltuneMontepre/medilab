from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT_REGISTER

if TYPE_CHECKING:
    from medilab_model_types import Model_account_payment_register as AccountPaymentRegisterBase
else:
    AccountPaymentRegisterBase = object


# Ghi nhận thanh toán: Odoo's dialog that registers a payment of invoices.
class AccountPaymentRegister(models.TransientModel, AccountPaymentRegisterBase):
    _inherit = MODEL_ACCOUNT_PAYMENT_REGISTER

    def _create_payments(self):
        """Refuse a customer payment of laboratory invoices above what they still owe."""
        for wizard in self:
            owed = wizard._medilab_amount_owed()
            if owed is not None and wizard.currency_id.compare_amounts(wizard.amount, owed) > 0:
                raise UserError(self.env._("A payment cannot be more than the amount still owed."))
        return super()._create_payments()

    def _medilab_amount_owed(self):
        """What the selected laboratory invoices still owe in the wizard's currency, or None for other payments."""
        self.ensure_one()
        laboratory = self.line_ids.move_id.filtered("invoice_kind")
        if (
            not self.can_edit_wizard
            or not laboratory
            or self.partner_type != "customer"
            or self.payment_type != "inbound"
        ):
            return None
        if self.currency_id == self.source_currency_id:
            return self.source_amount_currency
        return self.company_currency_id._convert(
            self.source_amount, self.currency_id, self.company_id, self.payment_date
        )
