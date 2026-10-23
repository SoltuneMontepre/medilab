from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_SECTOR,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_SOURCE,
)


@tagged("post_install", "-at_install")
class TestAuditDocuments(AuditLookup, TransactionCase):
    def test_every_document_is_audited(self):
        self.assertEqual(
            self.unaudited_documents("sol_onboarding"),
            {
                MODEL_ONBOARDING_ORGANISATION,
                MODEL_ONBOARDING_SECTOR,
                MODEL_ONBOARDING_SNAPSHOT,
                MODEL_ONBOARDING_SOURCE,
            },
        )
