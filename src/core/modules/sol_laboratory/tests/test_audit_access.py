from odoo.exceptions import AccessError
from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_CHANGE,
    MODEL_AUDIT_ENTRY,
    MODEL_AUDIT_MIXIN,
    MODEL_REGULATION,
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
        audit_models = {MODEL_AUDIT_ENTRY, MODEL_AUDIT_CHANGE}
        documents = {
            name
            for name, model in self.env.registry.items()
            if name.startswith("medilab.") and not model._abstract and not model._transient and name not in audit_models
        }

        self.assertFalse(documents - set(self.env.registry[MODEL_AUDIT_MIXIN]._inherit_children))
