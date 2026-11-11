from typing import TYPE_CHECKING, Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    FINISHED_STATUSES,
    PORTAL_SUMMARY_ITEMS,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    STATUS_QUOTED,
    STATUS_SUBMITTED,
    STATUS_TESTING,
    STATUS_WAITING,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

CUSTOMER_STATUSES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_QUOTED, "Quoted"),
    (STATUS_WAITING, "Waiting"),
    (STATUS_TESTING, "Testing"),
    (STATUS_COMPLETED, "Completed"),
    (STATUS_CANCELLED, "Cancelled"),
]
# Test request statuses the customer sees as Testing, Completed or Cancelled; any other is Waiting.
REQUEST_STATUS_TO_CUSTOMER = {
    "testing": STATUS_TESTING,
    "awaiting_approval": STATUS_TESTING,
    "completed": STATUS_COMPLETED,
    "reported": STATUS_COMPLETED,
    "cancelled": STATUS_CANCELLED,
}


if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderBase
else:
    SaleOrderBase = object


# Đơn Hàng: what the customer sees of the order, and whom sales reaches about it.
class SaleOrderCustomer(models.Model, SaleOrderBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The status shown to the customer: draft, submitted, quoted, then waiting, testing, completed or cancelled.
        customer_status = fields.Selection(
            CUSTOMER_STATUSES, compute="_compute_customer_status", search="_search_customer_status"
        )
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
            return REQUEST_STATUS_TO_CUSTOMER.get((self.sudo().test_request_id.status or ""), STATUS_WAITING)
        return STATUS_QUOTED if self.sudo().quotation_ids else STATUS_SUBMITTED

    def _search_customer_status(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        matching = Domain.OR(self._customer_status_domain(status) for status in value)
        return matching if operator == "in" else ~matching

    @api.model
    def _customer_status_domain(self, status):
        """The orders the customer sees under the status, as _customer_status reads them."""
        if status == STATUS_DRAFT:
            return Domain("order_status", "=", STATUS_DRAFT)
        if status in (STATUS_SUBMITTED, STATUS_QUOTED):
            sent = Domain("order_status", "not in", (STATUS_DRAFT, STATUS_CONFIRMED, *FINISHED_STATUSES))
            return sent & Domain("quotation_ids", "!=" if status == STATUS_QUOTED else "=", False)
        confirmed = Domain("order_status", "=", STATUS_CONFIRMED)
        if status == STATUS_WAITING:
            shown = list(REQUEST_STATUS_TO_CUSTOMER)
            return confirmed & Domain("test_request_id", "not any", [("status", "in", shown)])
        requests = [request for request, shown in REQUEST_STATUS_TO_CUSTOMER.items() if shown == status]
        if not requests:
            return Domain.FALSE
        reached = confirmed & Domain("test_request_id.status", "in", requests)
        return reached | Domain("order_status", "=", status) if status in FINISHED_STATUSES else reached

    def _compute_access_url(self):
        result = super()._compute_access_url()
        for order in self:
            order.access_url = f"/orders/{order.id}"
        return result

    @api.model
    def _portal_orders_domain(self, user):
        commercial = user.partner_id.commercial_partner_id
        return ["|", ("customer_id", "child_of", commercial.id), ("partner_id", "child_of", commercial.id)]

    @api.model
    def _portal_filter_domain(self, status=None, search=None):
        """The orders of the order history's filters: a customer-facing status, and text found in the order number or
        in the name of a parameter or package the customer ordered. An empty or unknown filter keeps every order."""
        domain = Domain.TRUE
        if status in dict(CUSTOMER_STATUSES):
            domain &= Domain("customer_status", "=", status)
        if search := (search or "").strip():
            item = Domain(
                [
                    ("display_type", "=", False),
                    ("linked_line_id", "=", False),
                    ("product_id", "ilike", search),
                    "|",
                    ("product_id.product_tmpl_id.parameter_id", "!=", False),
                    ("product_id.product_tmpl_id.service_package_id", "!=", False),
                ]
            )
            domain &= Domain("name", "ilike", search) | Domain("order_line", "any", item)
        return domain

    @api.model
    def _portal_orders(self, user, limit: int | None = None, offset: int = 0, **filters) -> Self:
        """The quotations and orders of the portal user's customer that match the filters, newest first."""
        domain = Domain(self._portal_orders_domain(user)) & self._portal_filter_domain(**filters)
        return self.sudo().search(domain, order="id desc", limit=limit, offset=offset)

    @api.model
    def _portal_order_count(self, user, **filters):
        domain = Domain(self._portal_orders_domain(user)) & self._portal_filter_domain(**filters)
        return self.sudo().search_count(domain)

    def portal_summary(self):
        """The first catalog items of the order, and how many more it has."""
        self.ensure_one()
        names = self._catalog_lines().product_id.mapped("display_name")
        shown = format_list(self.env, names[:PORTAL_SUMMARY_ITEMS])
        if len(names) > PORTAL_SUMMARY_ITEMS:
            return self.env._("%(items)s and %(count)s more", items=shown, count=len(names) - PORTAL_SUMMARY_ITEMS)
        return shown

    def can_reorder(self):
        """A draft is still the cart; any other order of the customer can be reordered."""
        self.ensure_one()
        return self.order_status != STATUS_DRAFT

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
