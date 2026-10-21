from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SECTOR,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import ACTION_CREATE, STAGED_TO_REVIEW
from odoo.addons.sol_onboarding.constants.xml_ids import SOURCES_GROUP


# Bản Ghi Chờ Duyệt
class OnboardingStagedRecord(models.Model):
    _name = MODEL_ONBOARDING_STAGED_RECORD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Staged Record"
    _order = "id desc"
    _permission_actions = ("read", "edit")

    _source_key_index = models.Index("(source_id, kind, external_key)")
    _state_index = models.Index("(state)")
    _record_index = models.Index("(record_model, record_id)")

    # Kind of master data the record proposes.
    kind = fields.Selection(
        [
            ("certificate", "Certificate"),
            ("testing_field", "Testing Field"),
            ("testing_method", "Testing Method"),
            ("sample_type", "Sample Type"),
            ("test_parameter", "Test Parameter"),
            ("parameter_method", "Parameter Method"),
        ],
        string="Kind",
        required=True,
    )
    # The source the record comes from; only the developers see it.
    source_id = fields.Many2one(
        MODEL_ONBOARDING_SOURCE, string="Source", required=True, ondelete="restrict", groups=SOURCES_GROUP
    )
    # The run that staged the record.
    run_id = fields.Many2one(MODEL_ONBOARDING_RUN, string="Run", required=True, ondelete="restrict")
    # The document the record was read from.
    snapshot_id = fields.Many2one(MODEL_ONBOARDING_SNAPSHOT, string="Snapshot", required=True, ondelete="restrict")
    # Address of the page the record was read from.
    page_url = fields.Char(string="Page Address", related="snapshot_id.url", compute_sudo=True)
    # Time the page was fetched.
    page_fetched_at = fields.Datetime(string="Page Fetched At", related="snapshot_id.fetched_at", compute_sudo=True)
    # Key of the record at the source, such as a method's standard code.
    external_key = fields.Char(string="External Key", required=True)
    # SHA-256 of the source values, telling whether the source changed them.
    checksum = fields.Char(string="Checksum", required=True)
    # Values as the source gives them, unchanged.
    source_values = fields.Json(string="Source Values", required=True)
    # Values as the administrator edited them; empty until edited.
    edited_values = fields.Json(string="Edited Values")
    # Language of the source values, such as vi_VN.
    lang = fields.Char(string="Language", required=True)
    # The sector the source lists the record for.
    sector_id = fields.Many2one(MODEL_ONBOARDING_SECTOR, string="Sector", ondelete="restrict")
    # The staged record this one belongs to, such as the certificate of a method in its scope.
    parent_id = fields.Many2one(MODEL_ONBOARDING_STAGED_RECORD, string="Parent", ondelete="cascade")
    # Staged records that belong to this one.
    child_ids = fields.One2many(MODEL_ONBOARDING_STAGED_RECORD, "parent_id", string="Children")
    # Proposed action: create, link or update.
    action = fields.Selection(
        [("create", "Create"), ("link", "Link"), ("update", "Update")],
        string="Action",
        required=True,
        default=ACTION_CREATE,
    )
    # Model of the Laboratory record it matches or became.
    record_model = fields.Char(string="Record Model")
    # Row of the Laboratory record it matches or became.
    record_id = fields.Integer(string="Record ID")
    # True when the match is a name match the administrator has not confirmed.
    match_suggested = fields.Boolean(string="Suggested Match", default=False)
    # to_review, accepted, rejected or superseded.
    state = fields.Selection(
        [
            ("to_review", "To Review"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("superseded", "Superseded"),
        ],
        string="Status",
        required=True,
        default=STAGED_TO_REVIEW,
    )
    # Why the administrator rejected it.
    reject_reason = fields.Text(string="Reject Reason")
    # Message of the last refused accept.
    error = fields.Text(string="Error")
    # The user who accepted or rejected it.
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed By", ondelete="restrict")
    # Time it was accepted or rejected.
    reviewed_at = fields.Datetime(string="Reviewed At")
