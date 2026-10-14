import io
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_date, format_datetime
from odoo.tools.binary import BinaryBytes

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_AUDIT_REPORT, MODEL_RES_USERS
from odoo.addons.sol_laboratory.constants.xml_ids import AUDIT_REPORT_ACTION

FILTER_FIELDS = ("document_model", "action", "source")
# Keys of a report row, in the order of the columns.
COLUMNS = ("date", "user", "source", "action", "document_type", "document", "field", "old_value", "new_value", "note")
# The row of an entry without field changes.
NO_CHANGE = {"field": "", "old_value": "", "new_value": ""}


# Báo Cáo Nhật Ký Hoạt Động
class AuditReport(models.TransientModel):
    _name = MODEL_AUDIT_REPORT
    _description = "Audit Report"

    # First day of the period reported, in the user's time zone.
    date_from = fields.Date(string="From", required=True, default=fields.Date.context_today)
    # Last day of the period reported, in the user's time zone.
    date_to = fields.Date(string="To", required=True, default=fields.Date.context_today)
    # Only entries on documents of this type, when set.
    document_model = fields.Selection(selection="_selection_document_model", string="Document Type")
    # Only entries on documents whose name contains this text, when set.
    document_name = fields.Char(string="Document")
    # Only entries of this user, when set.
    user_id = fields.Many2one(MODEL_RES_USERS)
    # Only entries of this action, when set.
    action = fields.Selection(selection="_selection_action")
    # Only entries from this source, when set.
    source = fields.Selection(selection="_selection_source")
    # The exported spreadsheet, removed with the report.
    file = fields.Binary(attachment=False, readonly=True)
    # File name of the exported spreadsheet.
    file_name = fields.Char(readonly=True)

    _period_check = models.Constraint("CHECK(date_from <= date_to)", "The period must end on or after its first day.")

    @api.model
    def _selection_document_model(self):
        return self.env[MODEL_AUDIT_ENTRY]._selection_document_model()

    @api.model
    def _selection_action(self):
        return self.env[MODEL_AUDIT_ENTRY]._fields["action"]._description_selection(self.env)

    @api.model
    def _selection_source(self):
        return self.env[MODEL_AUDIT_ENTRY]._fields["source"]._description_selection(self.env)

    def action_print(self):
        # The report uses the internal layout, so Odoo's document layout setup is not asked for first.
        return self.env.ref(AUDIT_REPORT_ACTION).report_action(self, config=False)

    def action_export(self):
        import xlsxwriter  # Odoo ships it for its own spreadsheet exports.

        self.ensure_one()
        columns = self._columns()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet()
        header = workbook.add_format({"bold": True})
        for column, (_key, label) in enumerate(columns):
            sheet.write_string(0, column, label, header)
        for line, row in enumerate(self._rows(), start=1):
            for column, (key, _label) in enumerate(columns):
                sheet.write_string(line, column, row[key])
        workbook.close()
        file_name = self.env._("Audit report %(start)s - %(end)s.xlsx", start=self.date_from, end=self.date_to)
        self.write({"file": BinaryBytes(output.getvalue(), filename=file_name), "file_name": file_name})
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={self._name}&id={self.id}&field=file&filename_field=file_name&download=true",
            "target": "self",
        }

    def _columns(self):
        labels = [
            self.env._("Date"),
            self.env._("User"),
            self.env._("Source"),
            self.env._("Action"),
            self.env._("Document Type"),
            self.env._("Document"),
            self.env._("Field"),
            self.env._("Old Value"),
            self.env._("New Value"),
            self.env._("Note"),
        ]
        return list(zip(COLUMNS, labels, strict=True))

    def _period_label(self):
        self.ensure_one()
        return self.env._(
            "From %(start)s to %(end)s",
            start=format_date(self.env, self.date_from),
            end=format_date(self.env, self.date_to),
        )

    def _rows(self):
        """One row per change, and one per entry without changes, oldest first."""
        self.ensure_one()
        entries = self.env[MODEL_AUDIT_ENTRY].search(self._entry_domain(), order="create_date, id")
        labels = {
            field_name: dict(entries._fields[field_name]._description_selection(self.env))
            for field_name in ("source", "action", "document_model")
        }
        rows = []
        for entry in entries:
            entry_row = {
                "date": format_datetime(self.env, entry.create_date),
                "user": entry.user_id.name or "",
                "source": labels["source"][entry.source],
                "action": labels["action"][entry.action],
                "document_type": labels["document_model"].get(entry.document_model, entry.document_model or ""),
                "document": entry.document_name or "",
                "note": entry.note or "",
            }
            changes = [
                {"field": change.field_label, "old_value": change.old_value or "", "new_value": change.new_value or ""}
                for change in entry.change_ids
            ]
            rows += [{**entry_row, **change} for change in changes or [NO_CHANGE]]
        return rows

    def _entry_domain(self):
        domain = Domain("create_date", ">=", self._utc_start(self.date_from)) & Domain(
            "create_date", "<", self._utc_start(self.date_to + timedelta(days=1))
        )
        for field_name in FILTER_FIELDS:
            if self[field_name]:
                domain &= Domain(field_name, "=", self[field_name])
        if self.user_id:
            domain &= Domain("user_id", "=", self.user_id.id)
        if self.document_name:
            domain &= Domain("document_name", "ilike", self.document_name)
        return domain

    def _utc_start(self, day):
        # The start of the day in the user's time zone, as Odoo stores datetimes: in UTC without a zone.
        zone = ZoneInfo(self.env.user.tz or "UTC")
        return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC).replace(tzinfo=None)
