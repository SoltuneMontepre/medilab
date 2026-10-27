from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.approvals import (
    PURPOSE_CHANGE_REQUEST,
    STATE_APPLIED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_MIXIN,
    MODEL_CHANGE_REQUEST,
    MODEL_CODE_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    EVENT_CHANGE_REQUEST_APPROVED,
    EVENT_CHANGE_REQUEST_REJECTED,
)

# What the requester asks for; it cannot change once a signature stands.
CONTENT_FIELDS = frozenset({"document_model", "document_id", "requested_change", "reason"})
# The statuses of a request its chain has decided; no signature can be withdrawn then.
DECIDED_STATUSES = (STATE_APPROVED, STATE_REJECTED, STATE_APPLIED)


# Yêu Cầu Thay Đổi
class ChangeRequest(models.Model):
    _name = MODEL_CHANGE_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN, MODEL_APPROVAL_MIXIN]
    _description = "Change Request"
    _order = "id desc"
    _rec_name = "code"
    # Whoever can edit a document type raises change requests on it; requests are signed, never edited or deleted.
    _permission_actions = ("read", "sign")

    # Unique code from a sequence, such as YCTD.2026.0001.
    code = fields.Char(required=True, readonly=True, copy=False)
    # Technical name of the document to change, such as medilab.test.result.
    document_model = fields.Char(string="Document Type", required=True, readonly=True)
    # Id of the version of the document to change.
    document_id = fields.Many2oneReference(
        model_field="document_model", string="Document Id", required=True, readonly=True
    )
    # The document to change, by its name.
    document_name = fields.Char(string="Document", compute="_compute_document_name")
    # Person who asked for the change; when is the creation time.
    requested_by_id = fields.Many2one(
        MODEL_PERSON, string="Requested By", required=True, readonly=True, ondelete="restrict"
    )
    # What to change.
    requested_change = fields.Text(string="Change", required=True, readonly=True)
    # Why the change is needed.
    reason = fields.Text(required=True, readonly=True)
    # Requested while its chain signs, then approved, rejected or applied.
    status = fields.Selection(
        [
            (STATE_REQUESTED, "Requested"),
            (STATE_APPROVED, "Approved"),
            (STATE_REJECTED, "Rejected"),
            (STATE_APPLIED, "Applied"),
        ],
        required=True,
        default=STATE_REQUESTED,
        readonly=True,
        copy=False,
        index=True,
    )
    # Reason given when the request was rejected.
    rejection_reason = fields.Text(readonly=True, copy=False)
    # Id of the new version created when the change was applied.
    new_document_id = fields.Many2oneReference(
        model_field="document_model", string="New Version", readonly=True, copy=False
    )

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a change request must be unique.")
    _document_idx = models.Index("(document_model, document_id)")

    @api.depends("document_model", "document_id")
    def _compute_document_name(self):
        self.document_name = False
        # One browse per document type, so the names of a page of requests are read together.
        for model, requests in self.grouped("document_model").items():
            if model in self.env:
                documents = self.env[model].sudo().browse(requests.mapped("document_id"))
                for request, document in zip(requests, documents, strict=True):
                    request.document_name = document.display_name

    @api.model
    def _raise(self, document_model, document_id, requested_change, reason):
        """Raise a change request as the current person on a document whose process is completed; only people who can
        edit that type of document can."""
        person = self.env[MODEL_PERSON]._current()
        if not person:
            raise UserError(self.env._("Only a person can raise a change request."))
        if not (requested_change or "").strip() or not (reason or "").strip():
            raise UserError(self.env._("Say what to change and why."))
        if document_model not in self.env or not isinstance(
            self.env[document_model], self.env.registry[MODEL_APPROVAL_MIXIN]
        ):
            raise UserError(self.env._("Change requests are raised on signed documents only."))
        document = self.env[document_model].browse(document_id).exists()
        document._check_permission("edit")
        if not document.sudo()._change_request_open():
            raise UserError(self.env._("A change request is raised only on a document whose process is completed."))
        if not document._approval_chain(PURPOSE_CHANGE_REQUEST):
            raise UserError(self.env._("This document type has no change-request chain."))
        if self.sudo().search_count(
            [
                ("document_model", "=", document_model),
                ("document_id", "=", document.id),
                ("status", "=", STATE_REQUESTED),
            ],
            limit=1,
        ):
            raise UserError(self.env._("%s already has an open change request.", document.sudo().display_name))
        request = self.sudo().create(
            {
                "document_model": document_model,
                "document_id": document.id,
                "requested_by_id": person.id,
                "requested_change": requested_change,
                "reason": reason,
            }
        )
        return request.with_env(self.env)

    def action_open_document(self):
        self.ensure_one()
        return self._document()._get_records_action()

    def action_open_new_version(self):
        self.ensure_one()
        return self.env[self.document_model].browse(self.new_document_id)._get_records_action()

    def action_reject(self, reason):
        rejected = super().action_reject(reason)
        self.sudo().rejection_reason = reason
        return rejected

    def _document(self):
        self.ensure_one()
        return self.env[self.document_model].browse(self.document_id)

    def _apply(self):
        """Create the version of the document the approved request asks for, and tell the requester."""
        self.status = STATE_APPROVED
        document = self._document()
        if not document._change_request_open():
            raise UserError(self.env._("%s can no longer be changed; reject the request.", document.display_name))
        version = document._new_version(self)
        self.write({"status": STATE_APPLIED, "new_document_id": version.id})
        self._notify_requester(
            EVENT_CHANGE_REQUEST_APPROVED,
            lambda env: env._(
                "Change request %(code)s was approved: %(document)s has a new version to sign.",
                code=self.code,
                document=document.display_name,
            ),
        )

    def _notify_requester(self, code, body):
        # The requester reads the message in their own language.
        partner = self.sudo().requested_by_id.user_id.partner_id
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            code,
            self,
            f"change_request:{self.id}:{self.status}",
            body(self.with_context(lang=partner.lang).env),
            subject=self.code,
            partners=partner,
        )

    def _approval_chain(self, purpose=PURPOSE_CHANGE_REQUEST):
        # A change request is signed through the chain its document type has for change requests.
        return self.env[self.document_model]._approval_chain(purpose)

    def _approval_department(self):
        return self.sudo()._document()._approval_department()

    def _approval_content_fields(self):
        return CONTENT_FIELDS

    def _approval_process_completed(self):
        # A decision is final: a rejected request stays on record and a new one is raised instead.
        return self.status in DECIDED_STATUSES

    def _approval_set_state(self, state):
        if state == STATE_APPROVED:
            self._apply()
        else:
            self.status = STATE_REJECTED if state == STATE_REJECTED else STATE_REQUESTED

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        self._notify_requester(
            EVENT_CHANGE_REQUEST_REJECTED,
            lambda env: env._("Change request %(code)s was rejected: %(reason)s", code=self.code, reason=reason),
        )
