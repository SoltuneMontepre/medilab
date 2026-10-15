from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SUPPORT_REQUEST
from odoo.addons.sol_commerce.constants.support import (
    SUPPORT_ACTION,
    SUPPORT_ANSWERED,
    SUPPORT_CLOSED,
    SUPPORT_OPEN,
    SUPPORT_TRIGGER,
)
from odoo.addons.sol_commerce.constants.xml_ids import SUPPORT_EDIT_ACCESS, SUPPORT_READ_ACCESS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TASK,
)

COMMENT = "comment"
# Messages people write: on the portal or in the back office, and by e-mail reply.
WRITTEN_TYPES = (COMMENT, "email")
# Parameters with which Odoo opens a thread through a shared token or a signed link.
LINK_ACCESS_PARAMS = frozenset({"hash", "pid", "token"})
# A salesperson sees the requests they handle and those nobody has taken yet.
HANDLER_DOMAIN = "['|', ('handled_by_id', '=', user.id), ('handled_by_id', '=', False)]"


# Yêu Cầu Hỗ Trợ
class SupportRequest(models.Model):
    _name = MODEL_SUPPORT_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN, "mail.thread", "portal.mixin"]
    _description = "Support Request"
    _order = "id desc"
    _rec_names_search = ("code", "subject")
    _permission_actions = ("read", "create", "edit", "delete")
    # The customer writes on the request from the portal's chatter with read access only.
    _mail_post_access = "read"

    # Unique code of the request, such as HT.0001; filled from a sequence when it is opened.
    code = fields.Char(required=True, copy=False)
    # The customer who asks for help.
    customer_id = fields.Many2one(MODEL_CUSTOMER, string="Customer", required=True, ondelete="restrict", index=True)
    # The contact holding the customer's details, which the customer's orders name.
    customer_partner_id = fields.Many2one(related="customer_id.partner_id", string="Customer Contact")
    # The order the request is about; empty when it is about none.
    order_id = fields.Many2one(MODEL_SALE_ORDER, string="Order", ondelete="restrict", index="btree_not_null")
    # Short subject of the request.
    subject = fields.Char(required=True)
    # open, answered once support has replied and the customer has not written since, or closed.
    status = fields.Selection(
        [(SUPPORT_OPEN, "Open"), (SUPPORT_ANSWERED, "Answered"), (SUPPORT_CLOSED, "Closed")],
        required=True,
        default=SUPPORT_OPEN,
        index=True,
    )
    # The Odoo user who opened the request: the customer from the portal, or sales on their behalf.
    opened_by_id = fields.Many2one(
        "res.users", string="Opened By", required=True, ondelete="restrict", default=lambda self: self.env.user
    )
    # The salesperson handling the request: the order's salesperson, or whoever takes it; empty until then.
    handled_by_id = fields.Many2one("res.users", string="Handled By", ondelete="restrict", index="btree_not_null")
    # When the request was closed.
    closed_at = fields.Datetime(readonly=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a support request must be unique.")
    _customer_status_idx = models.Index("(customer_id, status)")

    @api.depends("code", "subject")
    def _compute_display_name(self):
        for request in self:
            request.display_name = f"{request.code} {request.subject}" if request.code else request.subject

    def _compute_access_url(self):
        result = super()._compute_access_url()
        for request in self:
            request.access_url = f"/support/{request.id}"
        return result

    @api.model
    def _get_thread_with_access(self, thread_id, **kwargs):
        # Only the customer's portal users and sales open a request; a shared token or signed link never does.
        params = {key: value for key, value in kwargs.items() if key not in LINK_ACCESS_PARAMS}
        return super()._get_thread_with_access(thread_id, **params)

    @api.constrains("order_id", "customer_id")
    def _check_order_customer(self):
        for request in self.filtered("order_id"):
            order = request.order_id.sudo()
            partners = (order.customer_id | order.partner_id).mapped("commercial_partner_id")
            if request.customer_id.partner_id.commercial_partner_id not in partners:
                raise ValidationError(self.env._("The order does not belong to this customer."))

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env[MODEL_SALE_ORDER].sudo()
        for vals in vals_list:
            order = orders.browse(vals.get("order_id"))
            if order and not vals.get("handled_by_id"):
                vals["handled_by_id"] = order.user_id.id
        requests = super().create(vals_list)
        for request in requests:
            request.sudo().message_subscribe(partner_ids=request._customer_partner().ids)
            if request.handled_by_id:
                request._handler_assigned()
        return requests

    def _customer_partner(self):
        """The contact who follows the request: the customer who opened it, or the customer's contact."""
        self.ensure_one()
        opener = self.opened_by_id.sudo()
        return opener.partner_id if opener.share else self.customer_id.partner_id

    def _handler_assigned(self):
        self.ensure_one()
        self.sudo().message_subscribe(partner_ids=self.handled_by_id.partner_id.ids)
        self._create_task()

    def _create_task(self):
        """A task in the handler's to-do list, when the handler is a person of the laboratory."""
        people = self.env[MODEL_PERSON].sudo()
        for request in self:
            person = people.search([("user_id", "=", request.handled_by_id.id)], limit=1)
            if person:
                self.env[MODEL_TASK]._create_for_event(SUPPORT_TRIGGER, request, assignee=person, note=request.subject)

    def action_take(self):
        """Give a request nobody handles to the current salesperson."""
        locked = self.sudo().try_lock_for_update()
        for request in self.sudo():
            if request not in locked or request.handled_by_id:
                raise UserError(self.env._("%s is already taken.", request.display_name))
            if request.status == SUPPORT_CLOSED:
                raise UserError(self.env._("%s is closed.", request.display_name))
        self.write({"handled_by_id": self.env.uid})
        for request in self:
            request._handler_assigned()
        return True

    def action_close(self):
        """Close a request once the customer's question is settled."""
        for request in self:
            if request.status == SUPPORT_CLOSED:
                raise UserError(self.env._("%s is already closed.", request.display_name))
        self.write({"status": SUPPORT_CLOSED, "closed_at": fields.Datetime.now()})
        self.env[MODEL_TASK]._close_for_document(self, SUPPORT_ACTION)
        return True

    def _mail_get_operation_for_mail_message_operation(self, message_operation):
        # The customer writes and uploads files on an open or answered request with read access. A closed request takes
        # messages and files only from those who can edit it, which a customer cannot.
        if message_operation == "create":
            return [(Domain("status", "!=", SUPPORT_CLOSED), "read"), (Domain.TRUE, "write")]
        return super()._mail_get_operation_for_mail_message_operation(message_operation)

    def _check_open_for_customer(self):
        if self.env.user.share and SUPPORT_CLOSED in self.sudo().mapped("status"):
            raise UserError(self.env._("This request is closed. Open a new request if you need more help."))

    def message_post(self, **kwargs):
        self._check_open_for_customer()
        return super().message_post(**kwargs)

    def _message_update_content(self, message, /, *, body, **kwargs):
        self._check_open_for_customer()
        return super()._message_update_content(message, body=body, **kwargs)

    def _message_post_after_hook(self, message):
        super()._message_post_after_hook(message)
        if message.message_type not in WRITTEN_TYPES or message.is_internal or message.subtype_id.internal:
            return
        author = message.author_id
        if author and author.commercial_partner_id == self.sudo().customer_id.partner_id.commercial_partner_id:
            self._customer_wrote()
            return
        # Only someone who may edit the request answers it: its handler, any salesperson while nobody has taken it,
        # and those who handle every request. Another employee's message changes nothing.
        staff = author.user_ids.filtered(lambda user: not user.share and self.with_user(user).has_access("write"))[:1]
        if staff:
            self._sales_replied(staff)

    def _customer_wrote(self):
        """A customer message on an answered request opens it again, back in the handler's to-do list."""
        request = self.sudo()
        if request.status != SUPPORT_ANSWERED:
            return
        request.write({"status": SUPPORT_OPEN})
        if request.handled_by_id:
            request._create_task()

    def _sales_replied(self, user):
        """A reply from sales answers the request; a salesperson who replies to an untaken request takes it."""
        request = self.sudo()
        if not request.handled_by_id:
            request.write({"handled_by_id": user.id})
            request.message_subscribe(partner_ids=user.partner_id.ids)
        if request.status == SUPPORT_OPEN:
            request.write({"status": SUPPORT_ANSWERED})
        self.env[MODEL_TASK]._close_for_document(request, SUPPORT_ACTION)

    @api.model
    def _scope_permission_accesses(self):
        """Limit the generated read and edit accesses to the requests a salesperson handles and the untaken ones.

        Generated accesses are not updated on upgrade, so the module's data calls this on install and on upgrade.
        """
        for xml_id in (SUPPORT_READ_ACCESS, SUPPORT_EDIT_ACCESS):
            access = self.env.ref(xml_id, raise_if_not_found=False)
            if access and access.domain != HANDLER_DOMAIN:
                access.sudo().write({"domain": HANDLER_DOMAIN})

    @api.model
    def _portal_customer(self):
        """The customer of the signed-in portal user."""
        partner = self.env.user.partner_id.commercial_partner_id
        customer = self.env[MODEL_CUSTOMER].sudo().search([("partner_id", "=", partner.id)], limit=1)
        if not customer:
            raise UserError(self.env._("You are not registered as a customer yet. Contact the laboratory."))
        return customer

    @api.model
    def _portal_order(self, order_id):
        """The signed-in customer's order the request is about, or no order when none is chosen."""
        orders = self.env[MODEL_SALE_ORDER].sudo()
        if not order_id:
            return orders
        order = orders.browse(int(order_id)).exists() if str(order_id).isdigit() else orders
        if not order or not order._owned_by(self.env.user):
            raise UserError(self.env._("This order is not yours."))
        return order

    @api.model
    def portal_requests(self):
        """The requests of the signed-in portal user's customer, newest first."""
        partner = self.env.user.partner_id.commercial_partner_id
        return self.sudo().search([("customer_id.partner_id", "=", partner.id)])

    @api.model
    def portal_request(self, request_id):
        """One request of the signed-in portal user's customer, or an empty recordset."""
        request = self.sudo().browse(request_id).exists()
        partner = self.env.user.partner_id.commercial_partner_id
        if not request or request.customer_id.partner_id != partner:
            return self.sudo().browse()
        return request

    @api.model
    def portal_open(self, subject, order_id, body, attachments=None):
        """Open a request from the portal with its first message, optionally about one of the customer's orders."""
        customer = self._portal_customer()
        subject = (subject or "").strip()
        if not subject:
            raise UserError(self.env._("Give the request a subject."))
        text = (body or "").strip()
        if not text:
            raise UserError(self.env._("Write your question."))
        order = self._portal_order(order_id)
        request = self.sudo().create(
            {"customer_id": customer.id, "order_id": order.id, "subject": subject, "opened_by_id": self.env.uid}
        )
        request.message_post(
            body=text,
            author_id=self.env.user.partner_id.id,
            message_type=COMMENT,
            subtype_xmlid="mail.mt_comment",
            attachments=attachments or [],
        )
        return request
