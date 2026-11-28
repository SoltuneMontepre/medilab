from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_list
from odoo.tools.misc import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SAMPLE_COLLECTION_START
from odoo.addons.sol_commerce.constants.orders import COLLECTION_DROP_OFF
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE

# The local hour an afternoon pickup starts from.
AFTERNOON_HOUR = 13

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_collection_start as SampleCollectionStartBase
else:
    SampleCollectionStartBase = object


# Bắt Đầu Thu Mẫu
class SampleCollectionStart(models.TransientModel, SampleCollectionStartBase):
    _name = MODEL_SAMPLE_COLLECTION_START
    _description = "Start Sample Collection"

    if not TYPE_CHECKING:
        # The confirmed order whose samples are collected.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
        # When sample delivery staff meet the customer to collect the samples.
        appointment = fields.Datetime(required=True)
        # Expected duration of the collection appointment in minutes.
        duration_minutes = fields.Integer(string="Duration (minutes)", required=True, default=60)
        # Computed end of the collection appointment from its start and duration.
        appointment_end = fields.Datetime(string="Ends At", compute="_compute_schedule_details")
        # Where the samples are collected; the customer's address unless Sales agreed another place.
        address = fields.Text(string="Collection Address", required=True)
        # Contact person and phone number to reach at collection.
        contact_summary = fields.Char(string="Contact", compute="_compute_order_context")
        # Expected samples and containers of the order's test request.
        samples_summary_html = fields.Html(string="Expected Samples", compute="_compute_order_context", sanitize=False)
        # Payment still due at collection when agreed on the quotation.
        balance_notice = fields.Char(compute="_compute_order_context")
        # Working-hours, turnaround or delivery-staff workload warning for the chosen appointment.
        schedule_warning = fields.Char(compute="_compute_schedule_details")
        # Sample delivery staff free for the whole appointment, including the travel buffer around it.
        staff_availability = fields.Char(string="Available Staff", compute="_compute_schedule_details")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id") or self.env.context.get("default_order_id"))
        if order and "address" in fields_list and not values.get("address"):
            values["address"] = order.sudo().collection_address or order.customer_id._display_address()
        if order.expected_collection_date and "appointment" in fields_list and not values.get("appointment"):
            part = order.sudo().collection_time
            values["appointment"] = self._pickup_appointment(order.expected_collection_date, part)
        return values

    def _pickup_appointment(self, day, part=False):
        """The start of the first working time in the company's working calendar from the pickup day agreed when
        sending the quotation, in the afternoon when the customer prefers it, or from now when that time has passed;
        False when none is found within a month."""
        zone = ZoneInfo(self.env.company.tz or "UTC")
        moment = time(AFTERNOON_HOUR) if part == "afternoon" else time.min
        start = datetime.combine(day, moment, tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        start = max(start, fields.Datetime.now())
        intervals = (
            self.env[MODEL_MACHINE_BOOKING]
            .sudo()
            ._working_time(self.env[MODEL_PERSON], start, start + timedelta(days=31))
        )
        return next((begin for begin, _finish in intervals if begin >= start), False)

    @api.depends("order_id")
    def _compute_order_context(self):
        for wizard in self:
            order = wizard.order_id.sudo()
            if not order:
                wizard.contact_summary = False
                wizard.balance_notice = False
                wizard.samples_summary_html = False
                continue
            contact = order.partner_id
            phone = contact.phone or contact.parent_id.phone
            wizard.contact_summary = f"{contact.name}, {phone}" if phone else (contact.name or False)
            balance = order._collection_balance_line(self.env)
            wizard.balance_notice = balance if isinstance(balance, str) else False
            samples = order.test_request_id.sample_ids.sorted("id")
            if not samples:
                wizard.samples_summary_html = False
                continue
            rows = Markup("").join(
                Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
                % (
                    escape(sample.code or ""),
                    escape(sample.customer_sample_name or ""),
                    escape(sample.sample_type_id.display_name or ""),
                    escape(order._sample_expected_quantity_summary(sample)),
                )
                for sample in samples
            )
            wizard.samples_summary_html = Markup(
                '<div class="bg-white border rounded-3 overflow-hidden">'
                '<table class="table table-sm align-middle mb-0">'
                '<thead class="table-light"><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead>'
                "<tbody>%s</tbody></table></div>"
            ) % (
                escape(self.env._("Lab Code")),
                escape(self.env._("Sample")),
                escape(self.env._("Sample Type")),
                escape(self.env._("Expected")),
                rows,
            )

    @api.depends("appointment", "duration_minutes", "order_id.committed_date", "order_id.turnaround_days")
    def _compute_schedule_details(self):
        for wizard in self:
            wizard.appointment_end = False
            wizard.schedule_warning = False
            wizard.staff_availability = False
            if not wizard.appointment:
                continue
            if wizard.duration_minutes <= 0:
                wizard.schedule_warning = self.env._("Give a collection duration above 0 minutes.")
                continue
            end = wizard.appointment + timedelta(minutes=wizard.duration_minutes)
            warnings, available = wizard._availability_warnings(wizard.appointment, end)
            wizard.appointment_end = end
            wizard.schedule_warning = " ".join(warnings) or False
            wizard.staff_availability = format_list(self.env, [person.name for person in available]) or False

    def _availability_warnings(self, start, end):
        """Return the timing, turnaround and delivery-staff capacity warnings for the chosen appointment window, and
        the sample delivery staff free for it."""
        warnings = []
        if self.order_id.sudo().collection_method == COLLECTION_DROP_OFF:
            warnings.append(self.env._("The customer said they bring the samples to the laboratory."))
        if start < fields.Datetime.now():
            warnings.append(self.env._("This appointment is in the past."))
        committed = self.order_id.committed_date
        turnaround = self.order_id.turnaround_days
        if committed and turnaround:
            zone = ZoneInfo(self.env.company.tz or "UTC")
            day = start.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date()
            ready = self.env[MODEL_TEST_REQUEST]._date_after_working_days(start, turnaround)
            if ready > committed:
                warnings.append(
                    self.env._(
                        "Samples collected on %(day)s return results on %(ready)s, after the expected return date "
                        "%(committed)s.",
                        day=format_date(self.env, day),
                        ready=format_date(self.env, ready),
                        committed=format_date(self.env, committed),
                    )
                )
        staff_warnings, available = self._staff_warnings(start, end)
        return warnings + staff_warnings, available

    def _staff_warnings(self, start, end):
        """Check company working hours and sample delivery staff availability including the travel buffer. Return the
        warnings and the staff free for the whole window."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        expected_seconds = (end - start).total_seconds()
        company_intervals = bookings._working_time(self.env[MODEL_PERSON], start, end)
        company_open = sum((finish - begin).total_seconds() for begin, finish in company_intervals) >= expected_seconds
        warnings = []
        if not company_open:
            warnings.append(self.env._("This time is outside standard working hours or on a company day off."))
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        staff = (
            task_type.role_id.person_ids.filtered(lambda person: bool(person.active and person.user_id))
            if task_type.route == "role"
            else self.env[MODEL_PERSON]
        )
        if not staff:
            return warnings, []
        buffer_minutes = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("collection_travel_minutes")
        buffer = timedelta(minutes=buffer_minutes)
        win_start, win_end = start - buffer, end + buffer
        tasks = self.env[MODEL_TASK].sudo()
        ends_after = Domain("planned_end", ">", win_start) | (
            Domain("planned_end", "=", False) & Domain("planned_start", ">", win_start)
        )
        overlap = Domain("type_id", "=", task_type.id) & Domain("planned_start", "<", win_end) & ends_after
        busy_staff = tasks.search(
            overlap & Domain("status", "in", ("assigned", "in_progress")) & Domain("assignee_id", "in", staff.ids)
        ).assignee_id
        available = [
            person
            for person in staff - busy_staff
            if sum((finish - begin).total_seconds() for begin, finish in bookings._working_time(person, start, end))
            >= expected_seconds
        ]
        if company_open and not available:
            if busy_staff:
                warnings.append(
                    self.env._(
                        "All sample delivery staff are busy or off around this time (%s).",
                        format_list(self.env, busy_staff.mapped("name")),
                    )
                )
            else:
                warnings.append(
                    self.env._("No sample delivery staff are available (on leave or outside schedule) at this time.")
                )
        elif available:
            open_count = tasks.search_count(overlap & Domain("status", "=", "open"))
            if open_count >= len(available):
                warnings.append(
                    self.env._(
                        "%(open)s unclaimed collection(s) already overlap this window (with %(buffer)s min travel "
                        "buffer) for %(free)s available staff.",
                        open=open_count,
                        buffer=buffer_minutes,
                        free=len(available),
                    )
                )
        return warnings, available

    def action_start(self):
        self.ensure_one()
        notification = self.order_id.action_start_sample_collection(
            self.appointment, self.address, self.duration_minutes
        )
        # Closing the dialog reloads the order, which then hides Start sample collection.
        notification["params"]["next"] = {"type": "ir.actions.act_window_close"}
        return notification
