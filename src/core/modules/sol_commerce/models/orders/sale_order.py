import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import format_list

from odoo.addons.sol_commerce.constants.models import (
    MODEL_CANCELLATION_REQUEST,
    MODEL_ORDER_SAMPLE,
    MODEL_QUOTATION,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.notifications import EVENT_ORDER_UPDATED
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_PAID_STATES,
    CUSTOMER_CANCELLABLE,
    FINISHED_STATUSES,
    FOLLOW_UP_BY_QUOTATION_STATUS,
    FOLLOW_UP_PAID,
    FOLLOW_UP_UNPAID,
    NOTIFIED_STATUSES,
    PORTAL_LOCKED_ORDER_FIELDS,
    QUOTATION_ACCEPTED,
    QUOTATION_DECLINED,
    QUOTATION_EXPIRED,
    QUOTATION_REPLACED,
    QUOTATION_SENT,
    REQUESTED,
    SOURCE_PORTAL,
    SOURCE_SALES,
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    STATUS_SUBMITTED,
)
from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER
from odoo.addons.sol_commerce.constants.xml_ids import QUOTATION_REPORT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_MAIL_MESSAGE, MODEL_PERMISSION_MIXIN

_logger = logging.getLogger(__name__)


# Đơn Hàng
class SaleOrder(models.Model):
    _name = MODEL_SALE_ORDER
    _inherit = [MODEL_SALE_ORDER, MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _permission_actions = ("read", "create", "edit", "delete")
    _audit_children = ("order_line", "quotation_ids", "sample_ids", "cancellation_request_ids", "support_request_ids")

    # The customer who orders: the company, or the individual when they order for themselves.
    customer_id = fields.Many2one("res.partner", string="Customer", ondelete="restrict", index=True)
    # The contact sales reaches about this order.
    partner_id = fields.Many2one(string="Contact")
    # portal when the customer built it, or sales when a salesperson created it for the customer.
    source = fields.Selection(
        [(SOURCE_PORTAL, "Portal"), (SOURCE_SALES, "Sales")],
        string="Order Source",
        required=True,
        default=SOURCE_PORTAL,
    )
    # draft, submitted, claimed, confirmed, completed or cancelled.
    order_status = fields.Selection(
        [
            (STATUS_DRAFT, "Draft"),
            (STATUS_SUBMITTED, "Submitted"),
            (STATUS_CLAIMED, "Claimed"),
            (STATUS_CONFIRMED, "Confirmed"),
            (STATUS_COMPLETED, "Completed"),
            (STATUS_CANCELLED, "Cancelled"),
        ],
        required=True,
        default=STATUS_DRAFT,
        index=True,
    )
    # When the customer submitted the order.
    submitted_at = fields.Datetime()
    # When a salesperson claimed the order.
    claimed_at = fields.Datetime()
    # The date the customer expects the results.
    expected_result_date = fields.Date()
    # The order this one was reordered from.
    reordered_from_id = fields.Many2one(MODEL_SALE_ORDER, ondelete="set null", index=True)
    # Orders reordered from this one.
    reorder_ids = fields.One2many(MODEL_SALE_ORDER, "reordered_from_id")
    # Catalog items left out of this reorder because they are no longer sold.
    reorder_note = fields.Text(copy=False)
    # Total of the catalog prices times their quantities, excluding VAT.
    catalog_total = fields.Monetary(compute="_compute_catalog_total")
    # Cancellation requests on the order.
    cancellation_request_ids = fields.One2many(MODEL_CANCELLATION_REQUEST, "order_id")
    # When the advance must be paid; 3 days after sending by default, set by sales.
    payment_deadline = fields.Datetime(copy=False)
    # online, bank_transfer, cash, or none when the Head of Sales sends without an advance.
    advance_method = fields.Selection(
        [("online", "Online"), ("bank_transfer", "Bank transfer"), ("cash", "Cash"), ("none", "No advance")]
    )
    # full, percentage or fixed.
    advance_mode = fields.Selection([("full", "Full amount"), ("percentage", "Percentage"), ("fixed", "Fixed amount")])
    # The percentage or fixed amount of the advance, depending on the advance mode.
    advance_value = fields.Float()
    # Samples the customer will send.
    sample_ids = fields.One2many(MODEL_ORDER_SAMPLE, "order_id", string="Samples")
    # Quotations sent for the order, one per revision.
    quotation_ids = fields.One2many(MODEL_QUOTATION, "order_id", string="Quotations")
    # Where the latest quotation stands: unpaid until the advance is paid, declined or expired; empty when none was sent.
    quotation_follow_up = fields.Selection(
        [
            (FOLLOW_UP_UNPAID, "Unpaid"),
            (FOLLOW_UP_PAID, "Paid"),
            (QUOTATION_DECLINED, "Declined"),
            (QUOTATION_EXPIRED, "Expired"),
        ],
        compute="_compute_quotation_follow_up",
        store=True,
        index="btree_not_null",
    )
    _customer_status_idx = models.Index("(customer_id, order_status)")
    _status_submitted_idx = models.Index("(order_status, submitted_at)")
    _salesperson_status_idx = models.Index("(user_id, order_status)")

    @api.depends(
        "order_line.price_unit", "order_line.product_uom_qty", "order_line.display_type", "order_line.product_id"
    )
    def _compute_catalog_total(self):
        for order in self:
            order.catalog_total = sum(line.price_unit * line.product_uom_qty for line in order._catalog_lines())

    def _catalog_lines(self):
        return self.order_line._catalog_lines()

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if self.env.context.get("medilab_sales_order"):
            vals.update(
                {
                    "source": SOURCE_SALES,
                    "user_id": self.env.uid,
                    "order_status": STATUS_CLAIMED,
                    "claimed_at": fields.Datetime.now(),
                }
            )
        return vals

    def _compute_user_id(self):
        # Odoo falls back to the current user only for its own salesman group. A salesperson creating an order
        # on the orders screen keeps it when the contact changes.
        result = super()._compute_user_id()
        if self.env.context.get("medilab_sales_order"):
            for order in self.filtered(lambda order: not order.user_id and not order._origin.id):
                order.user_id = self.env.user
        return result

    @api.model_create_multi
    def create(self, vals_list):
        self._fill_create_values(vals_list)
        wanted_users = [vals.get("user_id") for vals in vals_list]
        orders = super().create(vals_list)
        for order, user_id in zip(orders, wanted_users, strict=True):
            order._settle_user(user_id)
        # The catalog prices are the system's, so a salesperson who may not change the new order still locks them.
        orders.order_line.sudo()._lock_catalog_price()
        return orders

    def _fill_create_values(self, vals_list):
        """Default the source, salesperson and status of a sales order, and stamp the submission and claim times."""
        now = fields.Datetime.now()
        sales = self.env.context.get("medilab_sales_order")
        for vals in vals_list:
            if sales:
                vals.setdefault("source", SOURCE_SALES)
                vals.setdefault("user_id", self.env.uid)
                vals.setdefault("order_status", STATUS_CLAIMED)
            if vals.get("order_status") == STATUS_SUBMITTED and not vals.get("submitted_at"):
                vals["submitted_at"] = now
            if vals.get("order_status") == STATUS_CLAIMED and not vals.get("claimed_at"):
                vals["claimed_at"] = now

    def _settle_user(self, user_id):
        """Leave a portal order unassigned until it is claimed; give any other order the salesperson asked for."""
        if self.source == SOURCE_PORTAL and self.order_status in (STATUS_DRAFT, STATUS_SUBMITTED):
            if self.user_id:
                self.with_context(medilab_status_change=True).write({"user_id": False})
        elif user_id and self.user_id.id != user_id:
            self.write({"user_id": user_id})

    def write(self, vals):
        self._check_portal_write(vals)
        if "order_status" in vals and not self.env.context.get("medilab_status_change"):
            raise UserError(self.env._("Change the order status with its actions."))
        result = super().write(vals)
        if "payment_deadline" in vals:
            self._reopen_expired_quotations()
        return result

    def _check_portal_write(self, vals):
        if self.env.su or not self.env.user.share:
            return
        if PORTAL_LOCKED_ORDER_FIELDS & set(vals):
            raise AccessError(self.env._("You cannot change prices or internal fields of an order."))

    def _set_status(self, status, extra=None):
        vals = {"order_status": status, **(extra or {})}
        result = self.with_context(medilab_status_change=True).write(vals)
        if status in NOTIFIED_STATUSES:
            for order in self:
                order._notify_status(status)
        return result

    def _notify_status(self, status):
        """Tell the order's contact that the order was submitted, claimed or cancelled, once per status."""
        self.ensure_one()
        if not self.partner_id:
            return
        body = {
            STATUS_SUBMITTED: self.env._("Order %s was submitted.", self.name),
            STATUS_CLAIMED: self.env._("Order %s was claimed by the laboratory.", self.name),
            STATUS_CANCELLED: self.env._("Order %s was cancelled.", self.name),
        }[status]
        try:
            with self.env.cr.savepoint():
                self.env[MODEL_MAIL_MESSAGE].raise_event(
                    EVENT_ORDER_UPDATED, self.sudo(), f"order:{self.id}:{status}", body, partners=self.partner_id
                )
        except Exception:
            _logger.exception("Order notice was not queued")

    def customer_cancel_mode(self):
        self.ensure_one()
        if self.order_status == STATUS_CONFIRMED:
            return "request"
        if self.order_status in CUSTOMER_CANCELLABLE:
            return "cancel"
        return ""

    def open_cancellation_request(self):
        self.ensure_one()
        # The customer cannot read the request model; the order still knows its open request.
        return self.sudo().cancellation_request_ids.filtered(lambda request: request.status == REQUESTED)[:1]

    def _owned_by(self, user):
        self.ensure_one()
        if user._is_public():
            return False
        commercial = user.partner_id.commercial_partner_id
        partners = (self.customer_id | self.partner_id).mapped("commercial_partner_id")
        return commercial in partners

    def _check_customer_owner(self):
        if self.env.su:
            return
        others = self.filtered(lambda order: not order._owned_by(self.env.user))
        if others:
            raise AccessError(self.env._("This order is not yours."))

    def add_catalog_product(self, product, quantity=1):
        """Add a parameter or package to the cart, or raise its quantity."""
        self.ensure_one()
        if self.order_status != STATUS_DRAFT:
            raise UserError(self.env._("Only a draft order can be changed."))
        product = product.sudo()
        if not product.sale_ok or not (product.parameter_id or product.service_package_id):
            raise UserError(self.env._("This item is not in the catalog."))
        if quantity < 1:
            raise UserError(self.env._("A catalog line needs a quantity of at least 1."))
        variant = product.product_variant_ids[:1]
        line = self._catalog_lines().filtered(lambda item: item.product_id == variant)[:1]
        if line:
            line.product_uom_qty += quantity
        else:
            self.env["sale.order.line"].sudo().create(
                {"order_id": self.id, "product_id": variant.id, "product_uom_qty": quantity}
            )
        self._catalog_lines()._lock_catalog_price()
        return self

    def action_submit(self, visitor=None):
        """Put the cart in the sales queue. A visitor gives their details and e-mail address first."""
        for order in self:
            if order.order_status != STATUS_DRAFT:
                raise UserError(self.env._("Only a draft order can be submitted."))
            if not order._catalog_lines():
                raise UserError(self.env._("Add at least one parameter or service package."))
            if not order.customer_id:
                order.sudo()._attach_visitor(visitor or {})
        self.sudo()._set_status(STATUS_SUBMITTED, {"submitted_at": fields.Datetime.now(), "user_id": False})
        return True

    def _attach_visitor(self, visitor):
        self.ensure_one()
        name = (visitor.get("name") or "").strip()
        email = (visitor.get("email") or "").strip()
        if not email:
            raise UserError(self.env._("Enter an e-mail address."))
        if not name:
            raise UserError(self.env._("Enter your name."))
        partner = (
            self.env["res.partner"]
            .sudo()
            .create({"name": name, "email": email, "phone": (visitor.get("phone") or "").strip()})
        )
        self.with_context(medilab_status_change=True).write({"partner_id": partner.id, "customer_id": partner.id})

    def action_claim(self):
        """Give the submitted order to the current salesperson. An unclaimed order has no owner yet, so a salesperson
        who may only edit their own orders claims it with full rights once they may read it and edit orders."""
        self.check_access("read")
        if not self._has_permission("edit"):
            raise AccessError(self.env._("You are not allowed to claim orders."))
        for order in self:
            if order.order_status != STATUS_SUBMITTED or order.user_id:
                raise UserError(self.env._("This order is already claimed."))
        self.sudo()._set_status(STATUS_CLAIMED, {"user_id": self.env.uid, "claimed_at": fields.Datetime.now()})
        return True

    def action_customer_cancel(self):
        """Cancel until the order is confirmed."""
        self._check_customer_owner()
        for order in self:
            if order.order_status == STATUS_CONFIRMED:
                raise UserError(self.env._("A confirmed order cannot be cancelled directly."))
            if order.order_status not in CUSTOMER_CANCELLABLE:
                raise UserError(self.env._("This order cannot be cancelled."))
        return self.sudo()._cancel_order()

    def action_sales_cancel(self):
        """Cancel an order sales owns, including a confirmed one the laboratory has not finished."""
        for order in self:
            if order.order_status in FINISHED_STATUSES:
                raise UserError(self.env._("This order cannot be cancelled."))
            message = order._cancellation_block_message() if order.order_status == STATUS_CONFIRMED else False
            if message:
                raise UserError(message)
        return self._cancel_order()

    def action_cancel(self):
        """Odoo's own cancellation goes through the same checks as the order's."""
        return self.action_sales_cancel()

    def _cancel_order(self):
        # Every cancellation, by sales or by accepting a request, respects Odoo's lock.
        if any(order.locked for order in self):
            raise UserError(self.env._("You cannot cancel a locked order. Please unlock it first."))
        self._cancel_laboratory_documents()
        self._set_status(STATUS_CANCELLED)
        cancellable = self.filtered(lambda order: order.state != "cancel")
        if cancellable:
            # Reading invoices to cancel drafts needs accounting access the salesperson does not have.
            cancellable.sudo()._action_cancel()
        return True

    def _cancel_laboratory_documents(self):
        """Cancel the test request and everything under it, once that model exists."""
        if "medilab.test.request" not in self.env:
            return
        return

    def _laboratory_blocks_cancellation(self):
        """True once a test of the order's request is approved."""
        self.ensure_one()
        return "approved" in self.sudo().test_request_id.sample_ids.test_ids.mapped("status")

    def _samples_collected(self):
        """True once the laboratory received a sample of the order's request."""
        self.ensure_one()
        return any(self.sudo().test_request_id.sample_ids.mapped("received_at"))

    def _cancellation_block_message(self):
        """Why sales cannot cancel the order on their own; empty when they can."""
        self.ensure_one()
        if self.order_status == STATUS_COMPLETED or self._laboratory_blocks_cancellation():
            return self.env._(
                "Testing is completed or results are released, so this order cannot be cancelled. "
                "The laboratory will contact you."
            )
        if self._samples_collected():
            return self.env._(
                "The samples of this order are collected, so cancelling it needs a change request "
                "the Head of Sales approves."
            )
        return False

    def action_reorder(self):
        """Create a draft with the same parameters and packages at current prices."""
        self.ensure_one()
        self._check_customer_owner()
        if not self.can_reorder():
            raise UserError(self.env._("A draft is changed in the cart, not reordered."))
        omitted = []
        commands = []
        for line in self._catalog_lines():
            product = line.product_id.product_tmpl_id
            if not product.sale_ok:
                omitted.append(product.display_name)
                continue
            commands.append(Command.create({"product_id": line.product_id.id, "product_uom_qty": line.product_uom_qty}))
        return self.sudo().create(
            {
                "partner_id": self.partner_id.id,
                "customer_id": self.customer_id.id,
                "source": SOURCE_PORTAL,
                "order_status": STATUS_DRAFT,
                "user_id": False,
                "reordered_from_id": self.id,
                "reorder_note": self._reorder_note(omitted),
                "order_line": commands,
            }
        )

    def _reorder_note(self, omitted):
        if not omitted:
            return False
        return self.env._(
            "These items are no longer in the catalog and were left out: %s",
            format_list(self.env, omitted),
        )

    def action_request_cancellation(self, reason):
        self.ensure_one()
        self._check_customer_owner()
        if self.order_status != STATUS_CONFIRMED:
            raise UserError(self.env._("Only a confirmed order that is not completed can be cancelled by request."))
        text = (reason or "").strip()
        if not text:
            raise UserError(self.env._("Give a reason for the cancellation."))
        if self.open_cancellation_request():
            raise UserError(self.env._("This order already has an open cancellation request."))
        return (
            self.env[MODEL_CANCELLATION_REQUEST]
            .sudo()
            .create({"order_id": self.id, "reason": text, "requested_by_id": self.env.uid})
        )

    @api.depends("quotation_ids.status", "quotation_ids.revision")
    def _compute_quotation_follow_up(self):
        for order in self:
            order.quotation_follow_up = FOLLOW_UP_BY_QUOTATION_STATUS.get(order._latest_quotation().status, False)

    def _latest_quotation(self):
        self.ensure_one()
        return self.sudo().quotation_ids.sorted("revision")[-1:]

    def action_send_quotation(self):
        """Store the next revision of the quotation as a PDF and mark the revision before it replaced."""
        self.check_access("write")
        for order in self:
            order._check_quotation_can_be_sent()
        for order in self:
            order._send_quotation()
        return True

    def _check_quotation_can_be_sent(self):
        self.ensure_one()
        if self.order_status in FINISHED_STATUSES:
            raise UserError(self.env._("This order cannot be quoted."))
        lines = self._catalog_lines()
        if not lines:
            raise UserError(self.env._("Add at least one parameter or service package before sending the quotation."))
        unassigned = lines.filtered(lambda line: not line.sample_id)
        if unassigned:
            raise UserError(
                self.env._(
                    "Give these items a sample before sending the quotation:\n%s",
                    "\n".join(unassigned.mapped("product_id.display_name")),
                )
            )
        latest = self._latest_quotation()
        if latest.status == QUOTATION_REPLACED:
            raise UserError(self.env._("A replaced quotation cannot be sent. Send the current revision instead."))
        if latest.status == QUOTATION_ACCEPTED:
            raise UserError(self.env._("An accepted quotation cannot be replaced."))
        if latest.status == QUOTATION_SENT and self.state != "draft":
            raise UserError(self.env._("This quotation was already sent. Revise it to send a new revision."))

    def _send_quotation(self):
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.payment_deadline or self.payment_deadline <= now:
            days = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_int(PAYMENT_DEADLINE_PARAMETER, DEFAULT_PAYMENT_DEADLINE_DAYS)
            )
            self.payment_deadline = now + timedelta(days=days)
        previous = self._latest_quotation()
        revision = previous.revision + 1
        code = self.env["ir.sequence"].sudo().next_by_code(MODEL_QUOTATION)
        quotation = (
            self.env[MODEL_QUOTATION]
            .sudo()
            .create(
                {
                    "code": code,
                    "order_id": self.id,
                    "revision": revision,
                    "replaces_id": previous.id,
                    "amount_total": self.amount_total,
                    "attachment_id": self._create_quotation_attachment(revision, code).id,
                }
            )
        )
        quotation.attachment_id.write({"res_model": MODEL_QUOTATION, "res_id": quotation.id})
        previous.write({"status": QUOTATION_REPLACED})
        if self.state == "draft":
            self.state = "sent"
        return quotation

    def _create_quotation_attachment(self, revision, code):
        self.ensure_one()
        report = self.env["ir.actions.report"].sudo().with_context(quotation_code=code)
        content, _report_type = report._render_qweb_pdf(QUOTATION_REPORT, self.ids)
        return (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": f"{self.name}-R{revision}.pdf",
                    "raw": content,
                    "mimetype": "application/pdf",
                    "res_model": MODEL_SALE_ORDER,
                    "res_id": self.id,
                }
            )
        )

    def action_revise_quotation(self):
        """Start a new revision; the next send stores it and replaces the current quotation."""
        self.check_access("write")
        for order in self:
            latest = order._latest_quotation()
            if not latest:
                raise UserError(self.env._("Send a quotation before revising it."))
            if latest.status == QUOTATION_ACCEPTED:
                raise UserError(self.env._("An accepted quotation cannot be revised."))
            if latest._is_advance_touched():
                raise UserError(self.env._("The customer has paid the advance, so this quotation cannot be revised."))
        for order in self:
            order._latest_quotation()._cancel_advance_invoice()
        self.filtered(lambda order: order.state == "sent").write({"state": "draft"})
        return True

    def _reopen_expired_quotations(self):
        """Moving the payment deadline into the future makes an expired quotation sent again."""
        now = fields.Datetime.now()
        for order in self.filtered(lambda item: item.payment_deadline and item.payment_deadline > now):
            latest = order._latest_quotation()
            if latest.status == QUOTATION_EXPIRED:
                latest.write({"status": QUOTATION_SENT})
                if latest.advance_invoice_id.payment_state in ADVANCE_PAID_STATES:
                    latest._accept()
