from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_REGULATION, MODEL_REGULATION_LIMIT


@tagged("post_install", "-at_install")
class TestAuditHistory(AuditCase):
    def test_the_history_of_a_regulation_shows_the_changes_to_its_limits(self):
        other = self.env[MODEL_REGULATION].create({"code": "QCVN 01-1:2018/BYT", "name": "Domestic water"})
        self.regulation.name = "Limits of heavy metals contamination in food"
        self.limit.max_value = 0.02
        other.name = "Clean water for domestic use"

        action = self.regulation.with_user(self.auditor).action_open_audit_history()
        history = self.env[MODEL_AUDIT_ENTRY].with_user(self.auditor).search(action["domain"])

        self.assertEqual(history, self.entries(self.regulation) | self.entries(self.limit))
        self.assertIn(self.entries(self.limit, "edit"), history)
        self.assertFalse(history & self.entries(other))

    def test_the_history_follows_the_documents_under_the_documents_under_it(self):
        # Like a test request, its samples and their sample tests: two levels below the document.
        self.patch(type(self.env[MODEL_REGULATION_LIMIT]), "_audit_children", ("parameter_id",))
        self.parameter.name = "Lead (Pb), total"

        action = self.regulation.action_open_audit_history()

        self.assertIn(self.entries(self.parameter, "edit"), self.env[MODEL_AUDIT_ENTRY].search(action["domain"]))
