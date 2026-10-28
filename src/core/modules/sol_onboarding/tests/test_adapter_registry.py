from odoo.tests import TransactionCase, tagged

from .pages_adapter import PagesAdapter
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE
from odoo.addons.sol_onboarding.services.adapters.registry import ADAPTERS, adapter_for


@tagged("post_install", "-at_install")
class TestAdapterRegistry(TransactionCase):
    def _source(self, adapter):
        return (
            self.env[MODEL_ONBOARDING_SOURCE]
            .sudo()
            .create({"name": "Lab", "adapter": adapter, "host": "lab.example", "start_url": "https://lab.example/"})
        )

    def test_a_registered_adapter_is_built_for_its_source(self):
        source = self._source("pages")
        adapter = adapter_for(source)
        self.assertIsInstance(adapter, PagesAdapter)
        self.assertEqual(adapter.organisation_list_pages(), ["https://lab.example/"])
        self.assertEqual(ADAPTERS["pages"], PagesAdapter)

    def test_an_unknown_adapter_is_refused(self):
        with self.assertRaises(ValueError):
            adapter_for(self._source("missing"))
