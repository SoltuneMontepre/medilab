from odoo.exceptions import AccessError
from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_EMPLOYEE,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_REGULATION,
    MODEL_SIGNATURE,
)

HISTORY_BUTTON = 'name="action_open_audit_history"'


@tagged("post_install", "-at_install")
class TestAuditAccess(AuditCase):
    def test_a_person_without_the_permission_cannot_see_the_trail_but_produces_entries(self):
        self.limit.with_user(self.editor).max_value = 0.02

        self.assertEqual(self.entries(self.limit, "edit").user_id, self.editor)
        with self.assertRaises(AccessError):
            self.env[MODEL_AUDIT_ENTRY].with_user(self.editor).search([])

    def test_an_auditor_reads_entries_and_their_changes(self):
        self.limit.max_value = 0.02

        entry = (
            self.env[MODEL_AUDIT_ENTRY]
            .with_user(self.auditor)
            .search(
                [
                    ("document_model", "=", self.limit._name),
                    ("document_id", "=", self.limit.id),
                    ("action", "=", "edit"),
                ]
            )
        )
        self.assertEqual(entry.change_ids.mapped("new_value"), ["0.02"])

    def test_only_auditors_see_the_history_button(self):
        regulations = self.env[MODEL_REGULATION]

        self.assertIn(HISTORY_BUTTON, regulations.with_user(self.auditor).get_view(view_type="form")["arch"])
        self.assertNotIn(HISTORY_BUTTON, regulations.with_user(self.editor).get_view(view_type="form")["arch"])

    def test_every_document_model_of_the_laboratory_is_audited(self):
        # The trail itself, and the records the trail already describes: signatures and the work of jobs.
        unaudited = {MODEL_AUDIT_ENTRY, MODEL_AUDIT_CHANGE, MODEL_SIGNATURE, MODEL_JOB_ITEM, MODEL_JOB_RUN}
        documents = {MODEL_EMPLOYEE, MODEL_DEPARTMENT} | {
            name
            for name, model in self.env.registry.items()
            if model._original_module == "sol_laboratory" and not model._abstract and not model._transient
        }
        mixin = self.env.registry[MODEL_AUDIT_MIXIN]
        audited = {
            name for name, model in self.env.registry.items() if issubclass(model, mixin) and not model._abstract
        }

        self.assertFalse(documents - unaudited - audited)
        self.assertFalse(unaudited & audited)
