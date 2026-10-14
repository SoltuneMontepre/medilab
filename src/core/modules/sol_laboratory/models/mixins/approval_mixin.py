from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_laboratory.constants.approvals import (
    APPROVAL_SYSTEM_CONTEXT,
    DECISION_REJECTED,
    DECISION_SIGNED,
    PURPOSE_SIGNING,
    STATE_APPROVED,
    STATE_NONE,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_PERSON,
    MODEL_SIGNATURE,
)


# Phê duyệt bằng chữ ký
class ApprovalMixin(models.AbstractModel):
    _name = MODEL_APPROVAL_MIXIN
    _description = "Approval by Signatures"

    # Version of the document that the next signature records; it grows when every signature is withdrawn.
    document_version = fields.Integer(default=1, copy=False)
    # True when the current user may sign the document now.
    approval_can_sign = fields.Boolean(compute="_compute_approval_actions")
    # True when the current user may reject the document now.
    approval_can_reject = fields.Boolean(compute="_compute_approval_actions")
    # True when the current user may withdraw their latest signature or rejection now.
    approval_can_withdraw = fields.Boolean(compute="_compute_approval_actions")

    def write(self, vals):
        content_fields = set(vals) & (self._approval_content_fields() | {"document_version"})
        if content_fields and not self.env.context.get(APPROVAL_SYSTEM_CONTEXT) and self._approval_has_standing():
            raise UserError(self.env._("The document has signatures; withdraw them before changing it."))
        return super().write(vals)

    @api.depends_context("uid")
    def _compute_approval_actions(self):
        for document in self:
            document.approval_can_sign = document._approval_allows(document._approval_check_actor)
            document.approval_can_reject = document._approval_allows(lambda: document._approval_check_actor(True))
            document.approval_can_withdraw = document._approval_allows(document._approval_check_withdraw)

    def action_sign(self):
        self.ensure_one()
        level = self._approval_check_actor()
        self._approval_record(level, DECISION_SIGNED)
        is_last = not level.chain_id.level_ids.filtered(lambda other: other.sequence > level.sequence)
        self.sudo()._approval_set_state(STATE_APPROVED if is_last else STATE_REQUESTED)

    def action_reject(self, reason):
        self.ensure_one()
        level = self._approval_check_actor(rejecting=True)
        if not (reason or "").strip():
            raise UserError(self.env._("A rejection needs a reason."))
        self._approval_record(level, DECISION_REJECTED, reason)
        self.sudo()._approval_set_state(STATE_REJECTED)
        self._approval_notify_rejected(reason)

    def action_withdraw(self):
        self.ensure_one()
        self._approval_own_row()._withdraw(process_completed=self._approval_process_completed())
        document = self.sudo()
        if document._approval_has_standing():
            document._approval_set_state(STATE_REQUESTED)
            return
        document._approval_restart()

    def _approval_restart(self):
        """Withdraw every signature and rejection that still stands and reopen the document, so it is signed again
        from the first level; the rows stay on record."""
        for document in self.sudo():
            document._approval_open_rows().write({"withdrawn_at": fields.Datetime.now()})
            document.with_context(**{APPROVAL_SYSTEM_CONTEXT: True}).write(
                {"document_version": document.document_version + 1}
            )
            document._approval_set_state(STATE_NONE)
            document._approval_reopened()

    def _approval_chain(self):
        return (
            self.env[MODEL_APPROVAL_CHAIN]
            .sudo()
            .search([("document_model", "=", self._name), ("purpose", "=", PURPOSE_SIGNING)], limit=1)
        )

    def _approval_requester(self):
        return self.env[MODEL_PERSON].browse()

    def _approval_department(self):
        return self.env[MODEL_DEPARTMENT].browse()

    def _approval_content_fields(self):
        return frozenset()

    def _approval_process_completed(self):
        return False

    def _approval_set_state(self, state):
        # Hosts keep their own status and store the approval state in it.
        pass

    def _approval_reopened(self):
        # Called when the last standing signature is withdrawn; hosts reopen their document here.
        pass

    def _approval_notify_rejected(self, reason):
        if hasattr(self, "message_post"):
            self.message_post(body=self.env._("The document was rejected: %s", reason))

    def _approval_open_rows(self):
        # Signatures and rejections of the document that are not withdrawn.
        self.ensure_one()
        return (
            self.env[MODEL_SIGNATURE]
            .sudo()
            .search(
                [
                    ("document_model", "=", self._name),
                    ("document_id", "=", self.id),
                    ("withdrawn_at", "=", False),
                ]
            )
        )

    def _approval_has_standing(self):
        return bool(
            self.env[MODEL_SIGNATURE]
            .sudo()
            .search_count(
                [
                    ("document_model", "=", self._name),
                    ("document_id", "in", self.ids),
                    ("decision", "=", DECISION_SIGNED),
                    ("withdrawn_at", "=", False),
                ],
                limit=1,
            )
        )

    def _approval_allows(self, check):
        if not self.id:
            return False
        try:
            check()
        except (UserError, AccessError):
            return False
        return True

    def _approval_check_actor(self, rejecting=False):
        # The level the current user signs or rejects at now; refuses when they cannot.
        self.ensure_one()
        chain = self._approval_chain()
        if not chain:
            raise UserError(self.env._("This document type has no approval chain."))
        rows = self._approval_open_rows()
        if rows.filtered(lambda row: row.decision == DECISION_REJECTED):
            raise UserError(self.env._("The document was rejected; withdraw the rejection first."))
        level = chain.level_ids.filtered(lambda other: other not in rows.level_id).sorted("sequence")[:1]
        if not level:
            raise UserError(self.env._("Every level has already signed."))
        person = self.env[MODEL_PERSON]._current()
        if level.role_id not in person.role_ids:
            raise UserError(self.env._("Only people with the role %s can act at this level.", level.role_id.name))
        self._check_permission("sign")
        department = self._approval_department()
        if level.same_department and (not department or person.department_id != department):
            raise UserError(self.env._("Only people of the department that did the work can act at this level."))
        if person in rows.signer_id:
            raise UserError(self.env._("You have already signed this document."))
        if rejecting and not level.can_reject:
            raise UserError(self.env._("This level cannot reject."))
        return level

    def _approval_own_row(self):
        # The latest signature or rejection of the current user that is not withdrawn.
        self.ensure_one()
        person = self.env[MODEL_PERSON]._current()
        row = (
            self._approval_open_rows().filtered(lambda other: other.signer_id == person).sorted("id", reverse=True)[:1]
        )
        if not row:
            raise UserError(self.env._("You have no signature on this document to withdraw."))
        return row

    def _approval_check_withdraw(self):
        self._approval_own_row()._check_withdrawable(self._approval_process_completed())

    def _approval_record(self, level, decision, reason=False):
        person = self.env[MODEL_PERSON]._current()
        self.env[MODEL_SIGNATURE].sudo().create(
            {
                "document_model": self._name,
                "document_id": self.id,
                "document_version": self.document_version,
                "level_id": level.id,
                "signer_id": person.id,
                "signer_name": person.name,
                "signer_role": level.role_id.name,
                "level_name": level.name,
                "decision": decision,
                "reason": reason,
            }
        )
