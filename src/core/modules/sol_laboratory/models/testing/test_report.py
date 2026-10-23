from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_date, formatLang

from odoo.addons.sol_laboratory.constants.approvals import (
    DECISION_SIGNED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_DIGITAL_SIGNING_MIXIN,
    MODEL_DOCUMENT_LOCK,
    MODEL_LOCK_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_QUALITY_REGISTRATION,
    MODEL_SIGNATURE,
    MODEL_TASK,
    MODEL_TEST_REPORT,
    MODEL_TEST_REQUEST,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_TEST_REPORT_DELIVERED, EVENT_TEST_REPORT_ISSUED
from odoo.addons.sol_laboratory.constants.signing import VERIFY_PATH
from odoo.addons.sol_laboratory.constants.tasks import REPORT_DRAFTED_TRIGGER
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT, TEST_RESULT_READER_GROUP

# The languages a report prints in, by the request's report language; a bilingual report puts them side by side.
PRINT_LANGS = {"vi": ("vi_VN",), "en": ("en_US",), "bilingual": ("vi_VN", "en_US")}
# The action of the lab head's signing task.
SIGNING_ACTION = "sign"
# The statuses of a report the lab head can still sign.
OPEN_STATUSES = ("draft", "signing")
# Samples left off the report: they have no results to report.
UNREPORTED_SAMPLE_STATUSES = ("cancelled", "rejected")


# Phiếu Kết Quả
class TestReport(models.Model):
    _name = MODEL_TEST_REPORT
    # Locked while edited. Signed through its approval chain, which the digital signing mixin brings, and issued
    # as a signed PDF.
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_DIGITAL_SIGNING_MIXIN]
    _description = "Test Report"
    _order = "id desc"
    # The system drafts and issues a report; people sign it and record its delivery, which edits it.
    _permission_actions = ("read", "edit", "sign")
    _digital_signing_report = TEST_REPORT_REPORT

    # Unique report number from a sequence, such as PKQ.2026.0001; given when the report is issued.
    code = fields.Char(string="Report Number", readonly=True, copy=False)
    # The test request reported.
    request_id = fields.Many2one(
        MODEL_TEST_REQUEST, string="Test Request", required=True, readonly=True, ondelete="restrict"
    )
    # The customer of the test request.
    customer_id = fields.Many2one(related="request_id.customer_id")
    # Version of the report, 1 for the first and one higher for each version a change request creates.
    version = fields.Integer(required=True, default=1, readonly=True, copy=False)
    # The version this report replaces; empty for version 1.
    replaces_id = fields.Many2one(MODEL_TEST_REPORT, readonly=True, copy=False, ondelete="restrict")
    # Where the report is in its signing.
    status = fields.Selection(
        [("draft", "Draft"), ("signing", "Signing"), ("issued", "Issued"), ("replaced", "Replaced")],
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )
    # Language the report is issued in, taken from the request: Vietnamese, English or both side by side.
    language = fields.Selection(
        [("vi", "Vietnamese"), ("en", "English"), ("bilingual", "Bilingual")], required=True, readonly=True
    )
    # When the report was issued.
    issued_at = fields.Datetime(readonly=True, copy=False)
    # The PDF of the issued report.
    attachment_id = fields.Many2one("ir.attachment", string="PDF", readonly=True, copy=False, ondelete="restrict")
    # How the report reaches the customer, as the request says.
    delivery_method = fields.Selection(related="request_id.delivery_method")
    # How to deliver when the method is other, or details such as the postal address.
    delivery_note = fields.Text(related="request_id.delivery_note")
    # The contact who receives the report: the request's recipient, or else the customer.
    recipient_id = fields.Many2one("res.partner", string="Recipient", compute="_compute_recipient_id")
    # When the report was delivered to the customer.
    delivered_at = fields.Datetime(readonly=True, copy=False)
    # Person who recorded the delivery.
    delivered_by_id = fields.Many2one(
        MODEL_PERSON, string="Delivered By", readonly=True, copy=False, ondelete="restrict"
    )
    # The reported results the report prints: those of the request's tests that are not cancelled.
    result_ids = fields.Many2many(
        MODEL_TEST_RESULT,
        string="Results",
        compute="_compute_result_ids",
        compute_sudo=True,
        groups=TEST_RESULT_READER_GROUP,
    )

    _code_unique = models.Constraint("UNIQUE(code)", "The number of a test report must be unique.")
    _version_unique = models.Constraint("UNIQUE(request_id, version)", "A test request has one report per version.")
    _replaces_unique = models.Constraint("UNIQUE(replaces_id)", "A report is replaced by one newer version.")

    @api.depends("code", "request_id.code")
    def _compute_display_name(self):
        for report in self:
            report.display_name = report.code or self.env._("Draft report of %s", report.sudo().request_id.code)

    @api.depends("request_id.report_recipient_id", "request_id.customer_id")
    def _compute_recipient_id(self):
        for report in self:
            request = report.sudo().request_id
            report.recipient_id = request.report_recipient_id or request.customer_id.partner_id

    @api.depends(
        "request_id.sample_ids.status",
        "request_id.sample_ids.test_ids.status",
        "request_id.sample_ids.test_ids.result_ids.is_reported",
        "request_id.sample_ids.test_ids.result_ids.is_replaced",
    )
    def _compute_result_ids(self):
        for report in self:
            samples = report.request_id.sample_ids.filtered(
                lambda sample: sample.status not in UNREPORTED_SAMPLE_STATUSES
            )
            tests = samples.test_ids.filtered(lambda test: test.status != "cancelled")
            report.result_ids = tests.result_ids.filtered(lambda result: result.is_reported and not result.is_replaced)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._("A test report changes only through its signing and delivery."))
        return super().write(vals)

    @api.model
    def _draft_for(self, requests):
        """Give each completed request its draft report, or start the signing of its rejected one again, and give the
        lab head a signing task."""
        reports = self.sudo().search([("request_id", "in", requests.ids), ("status", "in", OPEN_STATUSES)])
        # The lab head's rejection stays on record; the report is signed again from the first level.
        reports._approval_restart()
        drafted = requests.sudo() - reports.request_id
        reports |= self.sudo().create(
            [{"request_id": request.id, "language": request.report_language} for request in drafted]
        )
        tasks = self.env[MODEL_TASK]
        for report in reports:
            tasks._create_for_event(REPORT_DRAFTED_TRIGGER, document=report)
        return reports

    def action_reject(self, reason, results=None):
        """The lab head rejects the report, naming the results to check again; they go back to their department."""
        self.ensure_one()
        # A call through the API names the results by their ids.
        results = self.env[MODEL_TEST_RESULT].browse(getattr(results, "ids", results) or [])
        if not results:
            raise UserError(self.env._("Name the results to check again."))
        if results - self.sudo().result_ids:
            raise UserError(self.env._("Only results printed on the report can be checked again."))
        super().action_reject(reason)
        results.sudo()._send_back(
            self.env._("Report of %(request)s rejected: %(reason)s", request=self.sudo().request_id.code, reason=reason)
        )

    def action_record_delivery(self):
        self._check_permission("edit")
        # Sending the report by email is a long operation; a second click is refused while it runs.
        with self.env[MODEL_DOCUMENT_LOCK]._operation(self):
            self._record_delivery()

    def _record_delivery(self):
        person = self.env[MODEL_PERSON]._current()
        if not person:
            raise UserError(self.env._("Only a person can record a delivery."))
        reports = self.sudo()
        for report in reports:
            if report.status != "issued" or report.delivered_at:
                raise UserError(
                    self.env._("Only an issued report not delivered yet can be delivered: %s", report.display_name)
                )
            if not report.attachment_id:
                raise UserError(
                    self.env._("The PDF of %s waits for its digital signature; deliver it once signed.", report.code)
                )
            recipient = report.recipient_id
            if report.delivery_method == "email" and (not recipient.email or recipient.email_bounced):
                raise UserError(self.env._("%s has no email address to send the report to.", recipient.display_name))
        reports.write({"delivered_at": fields.Datetime.now(), "delivered_by_id": person.id})
        for report in reports.filtered(lambda report: report.delivery_method == "email"):
            recipient = report.recipient_id
            self.env[MODEL_MAIL_MESSAGE].raise_event(
                EVENT_TEST_REPORT_DELIVERED,
                report,
                f"test_report:{report.id}:delivered",
                report.with_context(lang=recipient.lang).env._("Test report %s is attached.", report.code),
                subject=report.code,
                partners=recipient,
                attachments=report.attachment_id,
            )

    def action_download(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    def action_print_draft(self):
        # The report does not use the company's document layout, so printing never asks to configure it.
        return self.env.ref(TEST_REPORT_REPORT).report_action(self, config=False)

    def _approval_check_actor(self, rejecting=False):
        report = self.sudo()
        # A new version is signed once the results it prints are approved; its request stays reported.
        ready = report.request_id.status == "completed" or (
            report.replaces_id and all(result.status == STATE_APPROVED for result in report.result_ids)
        )
        if self.status not in OPEN_STATUSES or not ready:
            raise UserError(self.env._("A report is signed once every result of its test request is approved."))
        return super()._approval_check_actor(rejecting)

    def _approval_process_completed(self):
        return self.status in ("issued", "replaced")

    def _change_request_open(self):
        return self.status == "issued"

    def _new_version(self, change_request):
        """Replace the issued report by its next version, a draft the lab head signs and issues again; the portal offers
        the issued version only."""
        self.ensure_one()
        report = self.sudo()
        report.status = "replaced"
        version = report.create(
            {
                "request_id": report.request_id.id,
                "language": report.request_id.report_language,
                "version": report.version + 1,
                "replaces_id": report.id,
            }
        )
        self.env[MODEL_TASK]._create_for_event(
            REPORT_DRAFTED_TRIGGER, document=version, note=change_request.requested_change
        )
        return version

    def _approval_set_state(self, state):
        if state == STATE_APPROVED:
            self._issue()
        elif state == STATE_REQUESTED:
            self.status = "signing"
        else:
            self.status = "draft"
        if state in (STATE_APPROVED, STATE_REJECTED):
            self.env[MODEL_TASK]._close_for_document(self, SIGNING_ACTION)

    def _issue(self):
        """Number the report, mark its request and samples reported, retain the kept samples, then store its PDF and
        tell the customer; with digital signing on, once Viettel Sign has signed the PDF."""
        self.ensure_one()
        self.write(
            {
                "code": self.code or self.env["ir.sequence"].next_by_code(MODEL_TEST_REPORT),
                "issued_at": fields.Datetime.now(),
                "status": "issued",
            }
        )
        request = self.request_id
        reported = request.sample_ids.filtered(lambda sample: sample.status == "completed")
        reported.status = "reported"
        reported._retain(self._report_day())
        if request.status != "reported":
            request._set_status("reported")
        if self._digital_signing_enabled():
            self._digital_signing_start()
            return
        pdf, _report_type = self.env["ir.actions.report"]._render_qweb_pdf(TEST_REPORT_REPORT, self.ids)
        self.attachment_id = self.env["ir.attachment"].create(
            {
                "name": self._digital_signing_filename(),
                "raw": pdf,
                "mimetype": "application/pdf",
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        self._notify_issued()

    def _digital_signing_fully_signed(self):
        return self.status in ("issued", "replaced")

    def _digital_signing_filename(self):
        return f"{self.code}.pdf"

    def _digital_signing_done(self, signature):
        self.sudo().attachment_id = signature.attachment_id
        self._notify_issued()

    def _notify_issued(self):
        """Tell the customer the results are released, once for each issued report."""
        self.ensure_one()
        event, document, partner, body = self._issued_notice()
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            event,
            document,
            f"test_report:{self.id}:issued",
            body,
            subject=self.code,
            partners=partner,
        )

    def _issued_notice(self):
        """The event raised, the document the results are released on, the contact told and the text in their
        language. E-commerce releases the results of an order on the order, to its contact."""
        request = self.request_id
        partner = request.customer_id.partner_id
        body = self.with_context(lang=partner.lang).env._(
            "The results of test request %(request)s are ready. Download report %(report)s from your portal.",
            request=request.code,
            report=self.code,
        )
        return EVENT_TEST_REPORT_ISSUED, self, partner, body

    @api.model
    def _portal_domain(self, user):
        """The issued reports of the portal user's customer; a replaced version is no longer offered."""
        customer = self.env[MODEL_CUSTOMER]._of_user(user)
        return Domain("status", "=", "issued") & Domain("request_id.customer_id", "=", customer.id)

    def _print_langs(self):
        return PRINT_LANGS[self.language]

    def _files_locked(self):
        """True when a report's PDF can no longer change: it is issued."""
        return any(report.status in ("issued", "replaced") for report in self)

    def _print_env(self):
        # Printing reads what the report shows with full rights; TestReportDocument checks who may print.
        return self.sudo().with_context(lang=self._print_langs()[0]).env

    def _in_langs(self, read):
        """What read(env) gives in each language of the report, side by side."""
        return _side_by_side(read(self.sudo().with_context(lang=lang).env) for lang in self._print_langs())

    def _report_day(self):
        """The day the report was issued, or today for a draft, in the laboratory's time zone."""
        return self._laboratory_day(self.issued_at or fields.Datetime.now())

    def _laboratory_day(self, moment):
        return fields.Datetime.context_timestamp(self.with_context(tz=self.env.company.tz or "UTC"), moment).date()

    def _print_labels(self):
        """The report's headings in its languages."""

        verify_url = f"{self.get_base_url()}{VERIFY_PATH}"

        def labels(env):
            _ = env._
            return {
                "title": _("Test Report"),
                "draft": _("Draft, not digitally signed"),
                "verify": _("Digitally signed. Verify this report at %s", verify_url),
                "number": _("Report No."),
                "request": _("Test Request"),
                "customer": _("Customer"),
                "address": _("Address"),
                "received": _("Samples Received"),
                "date": _("Report Date"),
                "sample": _("Sample"),
                "lab_code": _("Lab Code"),
                "conclusion": _("Conclusion"),
                "parameter": _("Parameter"),
                "result": _("Result"),
                "unit": _("Unit"),
                "limit": _("Limit"),
                "method": _("Method"),
                "signatures": _("Approved By"),
            }

        per_lang = [labels(self.with_context(lang=lang).env) for lang in self._print_langs()]
        return {key: _side_by_side(texts[key] for texts in per_lang) for key in per_lang[0]}

    def _print_header(self):
        """The customer, the dates and the numbers the report starts with."""
        report = self.sudo()
        env = report._print_env()
        partner = report.request_id.customer_id.partner_id
        address = (line.strip() for line in partner._display_address(without_name=True).splitlines())
        received = sorted(filter(None, report.result_ids.sample_id.mapped("received_at")))
        # The first and the last day samples arrived.
        received_days = [report._laboratory_day(moment) for moment in received[:1] + received[-1:]]
        return {
            "number": report.code or "",
            "request": report.request_id.code,
            "customer": partner.name,
            "address": ", ".join(filter(None, address)),
            "received": " – ".join(dict.fromkeys(format_date(env, day) for day in received_days)),
            "date": format_date(env, report._report_day()),
        }

    def _print_samples(self):
        """Each sample the report covers, with its conclusion and one row per reported result."""
        results = self.sudo().result_ids.sorted("id")
        ways = {result: result._way_of_testing() for result in results}
        marks = self._print_marks(self.env[MODEL_PARAMETER_METHOD].union(*ways.values()))
        env = self._print_env()
        return [
            {
                "name": sample.customer_sample_name,
                "code": sample.code,
                "conclusion": self._print_conclusion(sample, own),
                "rows": [self._print_row(result, ways[result], marks.get(ways[result], ""), env) for result in own],
            }
            for sample, own in sorted(results.grouped("sample_id").items(), key=lambda item: item[0].code)
        ]

    def _print_marks(self, ways):
        """The marks of the quality registrations valid on the report date, by the ways of testing they cover."""
        registrations = (
            self.env[MODEL_QUALITY_REGISTRATION]
            .sudo()
            .search(
                [
                    ("parameter_method_ids", "in", ways.ids),
                    ("report_mark", "!=", False),
                    "|",
                    ("valid_until", "=", False),
                    ("valid_until", ">=", self._report_day()),
                ]
            )
        )
        return {
            way: " ".join(
                registration.report_mark
                for registration in registrations.filtered(lambda r, way=way: way in r.parameter_method_ids)
                if registration.report_mark
            )
            for way in ways
        }

    def _print_conclusion(self, sample, results):
        regulation = sample.regulation_id
        if not regulation:
            return ""
        if "fail" in results.mapped("conclusion"):
            return self._in_langs(lambda env: env._("Does not meet %s", regulation.code))
        return self._in_langs(lambda env: env._("Meets %s", regulation.code))

    def _print_row(self, result, way, marks, env):
        parameter = self._in_langs(lambda lang_env: result.with_env(lang_env).parameter_id.name)
        return {
            "parameter": f"{parameter} {marks}".strip(),
            "result": self._in_langs(lambda lang_env: result.with_env(lang_env).value_text)
            or result.with_env(env).value_display,
            "unit": result.unit_id.name or "",
            "limit": self._print_limit(result, env),
            "method": way.method_id.code or "",
        }

    def _print_limit(self, result, env):
        if result.limit_text:
            return self._in_langs(lambda lang_env: result.with_env(lang_env).limit_text)
        low = result.limit_min_set and formatLang(env, result.limit_min, digits=result.limit_decimals)
        high = result.limit_max_set and formatLang(env, result.limit_max, digits=result.limit_decimals)
        if low and high:
            limit = f"{low} – {high}"
        elif high:
            limit = f"≤ {high}"
        elif low:
            limit = f"≥ {low}"
        else:
            return ""
        unit = result.limit_unit_id
        return f"{limit} {unit.name}" if unit and unit != result.unit_id else limit

    def _print_signers(self):
        """Who approved the results, then who signed the report; testers who only sent a result are left out."""
        report = self.sudo()
        rows = self.env[MODEL_SIGNATURE].sudo().search(
            [
                ("document_model", "=", MODEL_TEST_RESULT),
                ("document_id", "in", report.result_ids.ids),
                ("decision", "=", DECISION_SIGNED),
                ("withdrawn_at", "=", False),
                ("level_id", "not in", self.env[MODEL_TEST_RESULT]._approval_sending_level().ids),
            ]
        ) + report._approval_open_rows().filtered(lambda row: row.decision == DECISION_SIGNED).sorted("id")
        signers = {
            (row.signer_id.id, row.level_name): {"name": row.signer_name, "level": row.level_name} for row in rows
        }
        return list(signers.values())


def _side_by_side(texts):
    # A bilingual report shows each text in Vietnamese and English, once when both are the same.
    return " / ".join(dict.fromkeys(text for text in texts if text))
