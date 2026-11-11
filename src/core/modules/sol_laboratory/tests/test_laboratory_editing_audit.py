from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_AUDIT_CONTEXT, CALLBACK_AUDIT_ORIGIN
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY


@tagged("post_install", "-at_install")
class TestLaboratoryEditingAudit(LaboratoryEditingCase):
    def test_callback_provenance_is_scoped_and_cannot_be_forged_with_json_context(self):
        entries = self.env[MODEL_AUDIT_ENTRY].with_user(self.tester)
        self.assertEqual(entries._origin_values(), {"source": "screen", "user_id": self.tester.id})
        for value in (True, "api", {}, [], None):
            self.assertEqual(
                entries.with_context(**{CALLBACK_AUDIT_CONTEXT: value})._origin_values(),
                {"source": "screen", "user_id": self.tester.id},
            )
        self.assertEqual(
            entries.with_context(**{CALLBACK_AUDIT_CONTEXT: CALLBACK_AUDIT_ORIGIN})._origin_values(),
            {"source": "api", "user_id": False},
        )
        self.assertEqual(entries._origin_values(), {"source": "screen", "user_id": self.tester.id})
