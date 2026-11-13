from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ASSET, MODEL_IR_QWEB
from odoo.addons.sol_laboratory.models.system.ir_asset import ASSET_REVISION

BUNDLE = "web.assets_frontend_minimal"
REVISION = "odoo.addons.sol_laboratory.models.system.ir_asset.ASSET_REVISION"


@tagged("post_install", "-at_install")
class TestAssetRevision(TransactionCase):
    def version(self):
        return self.env[MODEL_IR_QWEB]._get_asset_bundle(BUNDLE, css=False, js=True).get_version("js")

    def test_raising_the_asset_revision_gives_a_bundle_a_new_address(self):
        current = self.version()

        with patch(REVISION, 2):
            raised = self.version()

        self.assertNotEqual(raised, current)

    def test_the_revision_is_added_to_the_time_of_each_file(self):
        paths = self.env[MODEL_IR_ASSET]._get_asset_paths(BUNDLE, {})

        with patch(REVISION, 0):
            unrevised = self.env[MODEL_IR_ASSET]._get_asset_paths(BUNDLE, {})

        self.assertTrue(paths)
        for (path, _full, _bundle, time), (same_path, _same_full, _same_bundle, original) in zip(
            paths, unrevised, strict=True
        ):
            self.assertEqual(path, same_path)
            if original is None:
                self.fail(f"{path} has no modification time")
            self.assertEqual(time, original + ASSET_REVISION)
