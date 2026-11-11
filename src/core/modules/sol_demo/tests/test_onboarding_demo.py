from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE


@tagged("post_install", "-at_install")
class TestOnboardingDemo(TransactionCase):
    def test_the_demo_turns_every_source_off(self):
        sources = self.env[MODEL_ONBOARDING_SOURCE].sudo().with_context(active_test=False)
        self.assertFalse(sources.search([("enabled", "=", True)]))
