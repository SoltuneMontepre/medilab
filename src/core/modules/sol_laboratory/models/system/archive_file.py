import gzip
import json
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.jobs import AUDIT_KIND, JOB_RUN_CONTEXT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_FILE,
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_JOB_RUN,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_archive_file as ArchiveFileBase
else:
    ArchiveFileBase = object


# Tệp Lưu Trữ
class ArchiveFile(models.Model, ArchiveFileBase):
    _name = MODEL_ARCHIVE_FILE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Archive File"
    _order = "period_start desc, id desc"
    # Archives are written by the cleanup job; administrators list and download them, and never change them.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # Kind of records archived, such as audit_entry.
        kind = fields.Selection([(AUDIT_KIND, "Audit Entries")], required=True, readonly=True)
        # First day of the period archived.
        period_start = fields.Date(required=True, readonly=True)
        # Last day of the period archived.
        period_end = fields.Date(required=True, readonly=True)
        # Number of records in the file.
        row_count = fields.Integer(required=True, readonly=True)
        # The Odoo attachment holding the file in object storage.
        attachment_id = fields.Many2one("ir.attachment", required=True, readonly=True, ondelete="restrict")
        # SHA-256 of the file, checked before the archived records are removed.
        checksum = fields.Char(string="SHA-256", required=True, readonly=True)
        # Size of the file in bytes.
        size_bytes = fields.Integer(string="Size (bytes)", required=True, readonly=True)
        # The cleanup run that wrote the file.
        job_run_id = fields.Many2one(MODEL_JOB_RUN, string="Job Run", required=True, readonly=True, ondelete="restrict")

    _period_unique = models.Constraint(
        "UNIQUE(kind, period_start, period_end)", "This period of records is already archived."
    )
    _attachment_unique = models.Constraint("UNIQUE(attachment_id)", "This file already belongs to an archive.")

    def _compute_display_name(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for archive in self:
            archive.display_name = f"{kinds.get(archive.kind)} {archive.period_start:%Y-%m}" if archive.kind else ""

    def action_download(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    @api.model
    def _audit_months_due(self, days):
        """The first days of the months whose audit entries are all older than the retention period of so many
        days, so each month is archived once, in one file."""
        first_open = (fields.Date.today() - timedelta(days=days)).replace(day=1)
        # Months are taken in UTC, as the archive of a month holds the entries of that UTC month.
        groups = (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .with_context(tz="UTC")
            ._read_group([("create_date", "<", first_open)], ["create_date:month"])
        )
        return [month.date() for [month] in groups]

    @api.model
    def _archive_audit_month(self, month):
        """Write the audit entries of the month, with their changes, to a compressed file of JSON lines, check the
        stored file against its SHA-256, and only then remove the entries."""
        start = datetime.combine(month, datetime.min.time())
        entries = (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .search([("create_date", ">=", start), ("create_date", "<", start + relativedelta(months=1))], order="id")
        )
        if not entries:
            return self.browse()
        # ponytail: one month of entries is built in memory; split the month into days if it outgrows a worker.
        data = gzip.compress("\n".join(json.dumps(row, default=str) for row in _audit_rows(entries)).encode())
        checksum = sha256(data).hexdigest()
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": f"{AUDIT_KIND}_{month:%Y-%m}.jsonl.gz",
                    "raw": data,
                    "mimetype": "application/gzip",
                    "res_model": self._name,
                }
            )
        )
        archive = self.sudo().create(
            {
                "kind": AUDIT_KIND,
                "period_start": month,
                "period_end": month + relativedelta(months=1, days=-1),
                "row_count": len(entries),
                "attachment_id": attachment.id,
                "checksum": checksum,
                "size_bytes": len(data),
                "job_run_id": self.env.context.get(JOB_RUN_CONTEXT),
            }
        )
        attachment.res_id = persisted_id(archive)
        attachment.invalidate_recordset(["raw"])
        if sha256(bytes(attachment.raw)).hexdigest() != checksum:
            raise UserError(self.env._("The archive file of %s does not match its checksum.", archive.display_name))
        entries._remove_archived()
        return archive


def _audit_rows(entries):
    # Each entry with its stored fields and its changes, as the trail recorded them.
    entry_fields = [name for name, field in entries._fields.items() if field.store and field.type != "one2many"]
    change_fields = [name for name, field in entries.change_ids._fields.items() if field.store]
    changes = defaultdict(list)
    for change in entries.change_ids.read(change_fields, load=None):
        changes[change["entry_id"]].append(change)
    for entry in entries.read(entry_fields):
        yield {**entry, "changes": changes[entry["id"]]}
