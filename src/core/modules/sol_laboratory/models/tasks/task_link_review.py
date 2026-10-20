from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_CHANGE, MODEL_AUDIT_ENTRY, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import (
    LINK_CHANGED,
    LINK_NOT_OF_TYPE,
    LINK_UNRECORDED,
    MANUAL_TRIGGER,
)
from odoo.addons.sol_laboratory.models.tasks.task import DOCUMENT_LINK_FIELDS, LINKED_BY_SYSTEM


# Nhiệm Vụ
class Task(models.Model):
    _inherit = MODEL_TASK

    @api.model
    def _verify_links_from_history(self):
        """Mark as linked by the system the tasks of event types that predate linked_by_system, when the audit trail
        records their creation and no later change to their type, document or action. Return them.

        Only evidence verifies a task: an empty history proves nothing, as a task may predate the trail or its entries
        may have been archived, so such a task stays unverified for an administrator to review.
        """
        tasks = self._unverified_links()
        findings = tasks._link_findings()
        verified = tasks.filtered(lambda task: task.type_id.trigger != MANUAL_TRIGGER and task.id not in findings)
        verified.write({LINKED_BY_SYSTEM: True})
        return verified

    @api.model
    def _link_review(self):
        """The tasks an administrator reviews, read-only: tasks of event types the system has not verified, and tasks
        made by hand that name a document or action their type does not. One row per task, with why it is listed and
        the document it names, with its sample for a sample test."""
        tasks = self._unverified_links()
        findings = tasks._link_findings()
        rows = []
        for task in tasks.filtered(lambda task: task.id in findings):
            model = task.document_model
            document = self.env[model].sudo().browse(task.document_id).exists() if model in self.env else None
            rows.append(
                {
                    "task_id": task.id,
                    "task": task.name,
                    "type": task.type_id.code,
                    "status": task.status,
                    "finding": findings[task.id],
                    "document_model": task.document_model,
                    "document_id": task.document_id,
                    "document": document.display_name if document else False,
                    "sample": document.sample_id.code if document and "sample_id" in document._fields else False,
                }
            )
        return rows

    @api.model
    def _unverified_links(self):
        tasks = self.sudo().search([(LINKED_BY_SYSTEM, "=", False), ("document_id", "!=", False)], order="id")
        return tasks.filtered("document_id")

    def _link_findings(self):
        """Why each task cannot be trusted, by task id, read from the audit trail in two queries for all of them. A
        task of an event type whose creation is recorded, with no later change to its link, is left out; so is a task
        made by hand that names its type's document, as it never acts on it with full rights."""
        tasks = Domain("document_model", "=", self._name) & Domain("document_id", "in", self.ids)
        recorded = set(
            self.env[MODEL_AUDIT_ENTRY].sudo().search(tasks & Domain("action", "=", "create")).mapped("document_id")
        )
        changed = set(
            self.env[MODEL_AUDIT_CHANGE]
            .sudo()
            .search(
                Domain("entry_id", "any", tasks & Domain("action", "=", "edit"))
                & Domain("field_name", "in", sorted(DOCUMENT_LINK_FIELDS))
            )
            .mapped("entry_id.document_id")
        )
        findings = {}
        for task in self.sudo():
            task_type = task.type_id
            if task.document_model != task_type.document_model or (task.action or False) != (task_type.action or False):
                findings[task.id] = LINK_NOT_OF_TYPE
            elif task_type.trigger == MANUAL_TRIGGER:
                continue
            elif task.id in changed:
                findings[task.id] = LINK_CHANGED
            elif task.id not in recorded:
                findings[task.id] = LINK_UNRECORDED
        return findings
