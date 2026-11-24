from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.misc import format_date, format_datetime

from odoo.addons.sol_commerce.constants.models import (
    MODEL_CUSTOMER_SALES_TERMS,
    MODEL_PAYMENT_REQUEST,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.notifications import EVENT_BALANCE_REQUESTED
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_NONE,
    BALANCE_AT_COLLECTION,
    BALANCE_BEFORE_COLLECTION,
    QUOTATION_ACCEPTED,
    QUOTATION_REPLACED,
    QUOTATION_SENT,
    SOURCE_SALES,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_MAIL_MESSAGE,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.services.staff_language import staff_env

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderConfirmationBase
else:
    SaleOrderConfirmationBase = object

# Ids of the orders that passed the checks and whose Odoo confirmation is running now. Only the code below fills it,
# so a caller cannot ask for the confirmation to skip the checks the way a context key would allow.
CONFIRMING_ORDER_IDS = ContextVar("medilab_confirming_order_ids", default=frozenset())
# Set by the Start sample collection button, which opens the dialog for the appointment and the place.
COLLECTION_DIALOG = "medilab_collection_dialog"
# Statuses of a test request whose samples have not arrived yet, while payment can still hold their collection.
AWAITING_SAMPLE_STATUSES = ("draft", "confirmed", "paid", "on_credit")


# Đơn Hàng: confirming the order creates its test request, whose sample collection sales then start.
class SaleOrderConfirmation(models.Model, SaleOrderConfirmationBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # True while a sample collection task of the order's test request is open.
        has_open_collection = fields.Boolean(compute="_compute_has_open_collection")
        # The open collection's appointment and who claimed it, for Sales, who cannot open the task.
        collection_summary = fields.Char(string="Sample Collection", compute="_compute_has_open_collection")
        # The test request the confirmed order produced.
        test_request_id = fields.Many2one(
            MODEL_TEST_REQUEST, string="Test Request", ondelete="restrict", copy=False, index="btree_not_null"
        )
        # True when this order was confirmed on the customer's approved credit terms.
        on_credit = fields.Boolean(readonly=True, copy=False)
        # True while the order's samples cannot be collected yet for want of payment.
        show_unpaid_warning = fields.Boolean(compute="_compute_show_unpaid_warning", compute_sudo=True)
        # What payment holds up on the confirmed order: its sample collection, or its report.
        payment_notice = fields.Char(compute="_compute_show_unpaid_warning", compute_sudo=True)
        # Processing and delivery state of the order's test result shown in the order header.
        result_status = fields.Selection(
            [
                ("collection_hold", "Awaiting sample payment"),
                ("awaiting_samples", "Awaiting samples"),
                ("in_progress", "Processing"),
                ("payment_hold", "Waiting for full payment"),
                ("ready", "Ready"),
                ("reported", "Sent"),
            ],
            string="Result",
            compute="_compute_show_unpaid_warning",
            compute_sudo=True,
        )
        # True once sample collection has logged at least one physical sample on the test request.
        has_collected_samples = fields.Boolean(compute="_compute_collected_samples_html", compute_sudo=True)
        # Read-only table of collected physical samples logged after sample collection for Sales to check.
        collected_samples_html = fields.Html(
            string="Collected Samples",
            compute="_compute_collected_samples_html",
            sanitize=False,
            compute_sudo=True,
        )

    @api.depends(
        "test_request_id.sample_ids.status",
        "test_request_id.sample_ids.received_at",
        "test_request_id.sample_ids.received_quantity",
        "test_request_id.sample_ids.condition",
        "test_request_id.sample_ids.physical_state",
    )
    def _compute_collected_samples_html(self):
        _ = self.env._
        status_badges = {
            "received": "text-bg-info",
            "testing": "text-bg-info",
            "awaiting_approval": "text-bg-warning",
            "on_hold": "text-bg-warning",
            "completed": "text-bg-success",
            "reported": "text-bg-success",
            "retained": "text-bg-secondary",
            "disposed": "text-bg-secondary",
            "returned": "text-bg-secondary",
            "rejected": "text-bg-danger",
            "cancelled": "text-bg-danger",
        }
        for order in self:
            samples = order.sudo().test_request_id.sample_ids.filtered(
                lambda s: s.status != "expected" or s.received_at or s.condition
            )
            if not samples:
                order.has_collected_samples = False
                order.collected_samples_html = False
                continue
            order.has_collected_samples = True
            states = dict(samples._fields["physical_state"]._description_selection(self.env))
            conditions = dict(samples._fields["condition"]._description_selection(self.env))
            statuses = dict(samples._fields["status"]._description_selection(self.env))
            rows = Markup("").join(
                Markup(
                    "<tr>"
                    '<td class="fw-semibold">%s</td>'
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<td>%s</td>"
                    '<td><span class="badge rounded-pill %s">%s</span></td>'
                    "</tr>"
                )
                % (
                    escape(sample.code or ""),
                    escape(sample.customer_sample_name or ""),
                    escape(sample.sample_type_id.display_name or ""),
                    escape(states.get(sample.physical_state, "") if sample.physical_state else ""),
                    escape(sample.received_quantity or ""),
                    escape(conditions.get(sample.condition, "") if sample.condition else ""),
                    escape(format_datetime(self.env, sample.received_at) if sample.received_at else ""),
                    status_badges.get(sample.status, "text-bg-secondary"),
                    escape(statuses.get(sample.status, sample.status or "")),
                )
                for sample in samples.sorted("id")
            )
            order.collected_samples_html = Markup(
                '<div class="bg-white border rounded-3 overflow-hidden">'
                '<table class="table table-sm align-middle mb-0">'
                '<thead class="table-light"><tr>'
                "<th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th>"
                "</tr></thead>"
                "<tbody>%s</tbody>"
                "</table></div>"
            ) % (
                escape(_("Lab Code")),
                escape(_("Sample")),
                escape(_("Sample Type")),
                escape(_("Physical State")),
                escape(_("Amount Received")),
                escape(_("Condition")),
                escape(_("Received At")),
                escape(_("Status")),
                rows,
            )

    @api.depends(
        "payment_status",
        "on_credit",
        "payment_request_ids.state",
        "balance_due",
        "order_status",
        "test_request_id.status",
    )
    def _compute_show_unpaid_warning(self):
        for order in self:
            hold = order._collection_hold()
            order.show_unpaid_warning = bool(hold)
            notice = False
            if order.order_status in (STATUS_CONFIRMED, STATUS_COMPLETED):
                notice = hold
                if not hold and order._withholds_report():
                    notice = self.env._(
                        "The report reaches the customer once the order is paid in full; %s is still due.",
                        order.currency_id.format(order.amount_total - order._verified_order_amount()),
                    )
            order.payment_notice = notice
            if order.order_status not in (STATUS_CONFIRMED, STATUS_COMPLETED):
                order.result_status = False
                continue
            test_status = order.sudo().test_request_id.status
            if test_status == "reported":
                order.result_status = "reported"
            elif test_status == "completed":
                order.result_status = "payment_hold" if order._withholds_report() else "ready"
            elif test_status in ("testing", "awaiting_approval"):
                order.result_status = "in_progress"
            elif hold:
                order.result_status = "collection_hold"
            else:
                order.result_status = "awaiting_samples"

    def _can_collect_samples(self):
        self.ensure_one()
        return not self._collection_hold()

    def _collection_hold(self):
        """Why the order's samples cannot be collected yet, or False: its advance is not verified, or Sales asked for
        the balance before collection and it is not paid. Otherwise the balance is due at collection or before the
        report, which waits until the order is paid. Nothing holds an order whose samples are in already."""
        self.ensure_one()
        if self.on_credit or self.payment_status == "paid" or self.currency_id.is_zero(self.amount_total):
            return False
        if self.order_status != STATUS_CONFIRMED or self.test_request_id.status not in AWAITING_SAMPLE_STATUSES:
            return False
        quotation = self._latest_quotation()
        advance = self.sudo().payment_request_ids.filtered(
            lambda ask: ask.kind == "advance" and ask.quotation_id == quotation
        )
        if not quotation or any(ask.state != "funded" for ask in advance):
            return self.env._("Verify the order's advance before collecting its samples.")
        if self.balance_due == BALANCE_BEFORE_COLLECTION:
            return self.env._("Verify the order balance before collecting its samples.")
        return False

    def _withholds_report(self):
        """Whether the order's report waits for payment: until the order is paid in full, unless the customer is on
        credit."""
        self.ensure_one()
        return not (self.on_credit or self.payment_status == "paid" or self.currency_id.is_zero(self.amount_total))

    def action_confirm(self):
        # Odoo's own Confirm button and every other caller go through the same checks.
        if self and set(self.ids) <= CONFIRMING_ORDER_IDS.get():
            return super().action_confirm()
        return self.action_confirm_order()

    def action_confirm_order(self):
        """Confirm the order the customer accepted and create its test request."""
        self.check_access("write")
        self._lock_payment_orders()
        for order in self:
            order._check_can_be_confirmed()
        for order in self:
            order._confirm_order()
        odoo_pending = self.filtered(lambda order: order.state in ("draft", "sent"))
        if odoo_pending:
            token = CONFIRMING_ORDER_IDS.set(CONFIRMING_ORDER_IDS.get() | frozenset(odoo_pending.ids))
            try:
                odoo_pending.action_confirm()
            finally:
                CONFIRMING_ORDER_IDS.reset(token)
        return True

    def _check_can_be_confirmed(self):
        self.ensure_one()
        latest = self._latest_quotation()
        # A new order is also draft. Revision is the draft that follows a quotation already sent.
        if self.state == "draft" and latest:
            raise UserError(self.env._("The quotation is being revised. Send the new revision first."))
        if self.order_status != STATUS_CLAIMED:
            raise UserError(self.env._("Only a claimed order can be confirmed."))
        if latest.status == QUOTATION_REPLACED:
            raise UserError(self.env._("A replaced quotation cannot be confirmed."))
        if latest.status != QUOTATION_ACCEPTED and not self._confirms_without_acceptance():
            raise UserError(self.env._("The customer must accept the quotation before the order is confirmed."))
        payment_request = self.sudo().payment_request_id
        if (
            payment_request.kind == "advance" and payment_request.state != "funded"
        ) or latest.sudo().advance_invoice_id.amount_residual:
            raise UserError(self.env._("Verify the full requested advance before confirming the order."))

    def _confirms_without_acceptance(self):
        """Whether Sales may confirm the sent quotation of an order Sales created and sent without an advance: the
        customer agreed it with Sales, at the counter or on the phone, and confirming accepts it."""
        self.ensure_one()
        latest = self._latest_quotation()
        return (
            self.source == SOURCE_SALES
            and self.advance_method == ADVANCE_NONE
            and latest.status == QUOTATION_SENT
            and not (self.payment_deadline and self.payment_deadline < fields.Datetime.now())
        )

    def _confirm_order(self):
        self.ensure_one()
        latest = self._latest_quotation()
        if latest.status == QUOTATION_SENT:
            latest._accept()
        customer = self.env[MODEL_CUSTOMER].sudo().search([("partner_id", "=", self.customer_id.id)], limit=1)
        if not customer:
            raise UserError(self.env._("%s is not a customer yet. Create the customer first.", self.customer_id.name))
        request = (
            self.env[MODEL_TEST_REQUEST]
            .sudo()
            .create_from_order(
                customer,
                [sample._test_request_values() for sample in self.sample_ids],
                committed_date=self.committed_date,
                requested_date=self.requested_date,
                priority=self.priority,
                turnaround_days=self.turnaround_days,
                report_recipient=self.partner_id if self.partner_id != self.customer_id else False,
            )
        )
        on_credit = self._qualifies_for_credit(customer)
        self.sudo().on_credit = on_credit
        self._set_status(STATUS_CONFIRMED, {"test_request_id": request.id, "confirmed_at": fields.Datetime.now()})
        if not on_credit:
            self._request_balance()
        request.action_confirm()

    def _qualifies_for_credit(self, customer):
        self.ensure_one()
        return self.advance_method == ADVANCE_NONE and bool(
            self.env[MODEL_CUSTOMER_SALES_TERMS]
            .sudo()
            .search_count([("customer_id", "=", customer.id), ("allow_credit", "=", True)], limit=1)
        )

    def _request_balance(self):
        self.ensure_one()
        amount = self.currency_id.round(self.amount_total - self._verified_order_amount())
        if amount <= 0:
            return
        request = (
            self.env[MODEL_PAYMENT_REQUEST]
            .sudo()
            .create(
                {
                    "kind": "balance",
                    "advance_method": self.payment_method,
                    "order_id": self.id,
                    "quotation_id": self._latest_quotation().id,
                    "amount": amount,
                    "carried_amount": self._verified_order_amount(),
                }
            )
        )
        self.sudo().payment_request_id = request
        order = self.with_context(lang=self._get_lang())
        values = {"amount": order.currency_id.format(amount), "order": order.name}
        if self.balance_due == BALANCE_BEFORE_COLLECTION:
            body = order.env._(
                "Pay the remaining %(amount)s for order %(order)s before its samples are collected.", **values
            )
        elif self.balance_due == BALANCE_AT_COLLECTION:
            body = order.env._(
                "Pay the remaining %(amount)s for order %(order)s when its samples are collected, online or to our "
                "staff. Its report is released once the order is paid in full.",
                **values,
            )
        else:
            body = order.env._(
                "Pay the remaining %(amount)s for order %(order)s. Its report is released once the order is paid in "
                "full.",
                **values,
            )
        order.env[MODEL_MAIL_MESSAGE].sudo().raise_event(
            EVENT_BALANCE_REQUESTED, order.sudo(), f"payment-request:{request.id}:sent", body, partners=order.partner_id
        )

    def _release_test_request(self):
        for request in self.sudo().test_request_id.filtered(lambda item: item.status == "confirmed"):
            request._set_status("paid")

    def _keep_order_numbers(self):
        """Write each order's number on its test request, which keeps it once uninstalling E-commerce drops the link."""
        for order in self.sudo().search([("test_request_id", "!=", False)]):
            order.test_request_id.order_number = order.name

    def _compute_has_open_collection(self):
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        tasks = self.env[MODEL_TASK].sudo()
        for order in self:
            request = order.sudo().test_request_id
            task = (
                tasks.search(
                    Domain("document_model", "=", request._name)
                    & Domain("document_id", "=", request.id)
                    & Domain("type_id", "=", task_type.id)
                    & tasks._in_use_domain(),
                    limit=1,
                )
                if request
                else tasks
            )
            order.has_open_collection = bool(task)
            summary = False
            if task:
                appointment = task.deadline
                summary = self.env._(
                    "%(appointment)s, %(who)s",
                    appointment=format_datetime(self.env, appointment, dt_format="short")
                    if appointment
                    else self.env._("no appointment"),
                    who=task.assignee_id.name or self.env._("not claimed yet"),
                )
            order.collection_summary = summary

    def _collection_place(self, address):
        """The address Sales entered, or else the customer's, on one line."""
        self.ensure_one()
        text = address if isinstance(address, str) and address else self.customer_id._display_address()
        return ", ".join(line.strip() for line in text.splitlines() if line.strip())

    def _collection_note(self):
        """What collection staff need beyond the time and the place, in the staff language: whom to contact and, when
        Sales asked for the balance at collection, the amount still due."""
        self.ensure_one()
        order = self.sudo()
        env = staff_env(self.env)
        contact = order.partner_id
        lines = [
            env._(
                "Contact: %(name)s, %(phone)s",
                name=contact.name,
                phone=contact.phone or contact.parent_id.phone or "-",
            )
        ]
        balance = order._collection_balance_line(env)
        if balance:
            lines.append(balance)
        return "\n".join(lines)

    def _collection_balance_line(self, env):
        self.ensure_one()
        order = self.sudo()
        due = order.payment_request_id
        if (
            order.on_credit
            or order.balance_due != BALANCE_AT_COLLECTION
            or due.kind != "balance"
            or not due.remaining_amount
        ):
            return False
        return env._(
            "Balance due at collection: %(amount)s. The customer pays it online from the link we sent them, or Sales "
            "records a cash payment.",
            amount=order.currency_id.format(due.remaining_amount),
        )

    def _check_collection_appointment(self, appointment):
        """Refuse an appointment in the past, or one too late for the turnaround to meet the expected return date."""
        self.ensure_one()
        if not appointment:
            return
        if appointment < fields.Datetime.now():
            raise UserError(self.env._("Agree a sample collection appointment that is still to come."))
        committed = self.committed_date
        if not (committed and self.turnaround_days):
            return
        zone = ZoneInfo(self.env.company.tz or "UTC")
        day = appointment.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date()
        ready = self.env[MODEL_TEST_REQUEST]._date_after_working_days(day, self.turnaround_days)
        if ready > committed:
            raise UserError(
                self.env._(
                    "Samples collected on %(day)s return results on %(ready)s, after the expected return date "
                    "%(committed)s. Agree an earlier appointment, or change the return date with the customer first.",
                    day=format_date(self.env, day),
                    ready=format_date(self.env, ready),
                    committed=format_date(self.env, committed),
                )
            )

    def action_start_sample_collection(self, appointment: datetime | bool = False, address: str | bool = False):
        """Queue one unassigned sample collection task of the confirmed order's test request for sample delivery
        staff, due at the appointment Sales agreed with the customer, at the address given or else the customer's."""
        self.check_access("write")
        appointment = fields.Datetime.to_datetime(appointment) or False
        for order in self:
            if order.order_status != STATUS_CONFIRMED:
                raise UserError(self.env._("The order must be confirmed before the samples are collected."))
            hold = order._collection_hold()
            if hold:
                raise UserError(hold)
        if self.env.context.get(COLLECTION_DIALOG) and not appointment:
            # The button asks Sales for the appointment and the place first.
            self.ensure_one()
            action = self.env["ir.actions.act_window"]._for_xml_id(
                "sol_commerce.action_medilab_sample_collection_start"
            )
            action["context"] = {"default_order_id": self.id}
            return action
        for order in self:
            order._check_collection_appointment(appointment)
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        if task_type.route != "role":
            raise UserError(
                self.env._("Route the %s task type to the role of sample delivery staff first.", task_type.name)
            )
        tasks = self.env[MODEL_TASK].sudo()
        for order in self:
            request = order.sudo().test_request_id
            document = Domain("document_model", "=", request._name) & Domain("document_id", "=", request.id)
            if tasks.search_count(document & Domain("type_id", "=", task_type.id) & tasks._in_use_domain(), limit=1):
                raise UserError(self.env._("Order %s already has an open sample collection task.", order.name))
            tasks.create(
                {
                    "type_id": task_type.id,
                    "name": f"{task_type.with_env(staff_env(self.env)).name}: {order.name}, {order.customer_id.name}",
                    "document_model": request._name,
                    "document_id": request.id,
                    "place": order._collection_place(address),
                    "note": order._collection_note(),
                    "deadline": appointment,
                    "planned_start": appointment,
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("The sample collection task waits in the queue of sample delivery staff."),
            },
        }
