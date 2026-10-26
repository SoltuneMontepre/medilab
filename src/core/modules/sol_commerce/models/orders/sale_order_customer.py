from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    STATUS_DRAFT,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

CUSTOMER_STATUSES = [
    (STATUS_DRAFT, "Draft"),
    ("submitted", "Submitted"),
    ("quoted", "Quoted"),
    ("waiting", "Waiting"),
    ("testing", "Testing"),
    (STATUS_COMPLETED, "Completed"),
    (STATUS_CANCELLED, "Cancelled"),
]
# Test request statuses the customer sees as Testing, Completed or Cancelled; any other is Waiting.
REQUEST_STATUS_TO_CUSTOMER = {
    "testing": "testing",
    "awaiting_approval": "testing",
    "completed": STATUS_COMPLETED,
    "reported": STATUS_COMPLETED,
    "cancelled": STATUS_CANCELLED,
}


# Đơn Hàng: what the customer sees of the order, and whom sales reaches about it.
class SaleOrderCustomer(models.Model):
    _inherit = MODEL_SALE_ORDER

    # The status shown to the customer: draft, submitted, quoted, then waiting, testing, completed or cancelled.
    customer_status = fields.Selection(CUSTOMER_STATUSES, compute="_compute_customer_status")
    # The status of the order's test request: the internal detail behind the status the customer sees.
    test_request_status = fields.Selection(related="test_request_id.status", string="Laboratory Status")
    # Whether the customer is a business with contacts to choose from; an individual is their own contact.
    customer_is_company = fields.Boolean(related="customer_id.is_company")
    # The number of the order's latest quotation, which its printed quotation carries; empty before one is sent.
    quotation_code = fields.Char(compute="_compute_quotation_code")

    @api.depends("quotation_ids.code", "quotation_ids.revision")
    def _compute_quotation_code(self):
        for order in self:
            order.quotation_code = order.sudo().quotation_ids.sorted("revision")[-1:].code

    @api.depends("order_status", "quotation_ids", "test_request_id.status")
    def _compute_customer_status(self):
        for order in self:
            order.customer_status = order._customer_status()

    def _customer_status(self):
        self.ensure_one()
        if self.order_status in (STATUS_DRAFT, STATUS_COMPLETED, STATUS_CANCELLED):
            return self.order_status
        if self.order_status == STATUS_CONFIRMED:
            return REQUEST_STATUS_TO_CUSTOMER.get(self.sudo().test_request_id.status, "waiting")
        return "quoted" if self.sudo().quotation_ids else "submitted"

    @api.model
    def _portal_orders(self, user):
        """Every quotation and order of the portal user's customer, newest first."""
        commercial = user.partner_id.commercial_partner_id
        return self.sudo().search(
            ["|", ("customer_id", "child_of", commercial.id), ("partner_id", "child_of", commercial.id)],
            order="id desc",
        )

    def _customer_record(self):
        self.ensure_one()
        return self.env[MODEL_CUSTOMER].sudo().search([("partner_id", "=", self.customer_id.id)], limit=1)

    def _contact_choices(self):
        """The people of a business customer its order's contact is chosen from; empty for an individual."""
        customer = self._customer_record()
        return customer._contacts() if customer.is_company else self.env["res.partner"]

    def set_portal_contact(self, contact_id):
        self.ensure_one()
        contact = self._contact_choices().filtered(lambda partner: partner.id == contact_id)
        if not contact:
            raise UserError(self.env._("Choose one of your company's contacts."))
        self.sudo().partner_id = contact

    @api.onchange("customer_id")
    def _onchange_customer_id_contact(self):
        if self.customer_id:
            self.partner_id = self._customer_record().default_contact_id or self.customer_id
