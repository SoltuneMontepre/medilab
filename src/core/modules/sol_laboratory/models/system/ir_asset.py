from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ASSET

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_asset as IrAssetBase
else:
    IrAssetBase = object

# Seconds added to the modification time of every asset file. A bundle's address is a hash of its files' paths and
# times, and Odoo serves a bundle as immutable for a year, so raising it gives every bundle an address browsers and the
# CDN have not cached yet.
ASSET_REVISION = 1


# Tài Nguyên Giao Diện
class IrAsset(models.Model, IrAssetBase):
    _inherit = MODEL_IR_ASSET

    def _get_asset_paths(self, bundle, assets_params):
        # A new list, as Odoo caches the one it returns.
        return [
            (path, full_path, definition_bundle, _revised(last_modified))
            for path, full_path, definition_bundle, last_modified in super()._get_asset_paths(bundle, assets_params)
        ]


def _revised(last_modified):
    # External assets have -1 and attachment addresses no time; neither is a file with a version.
    if last_modified is None or last_modified < 0:
        return last_modified
    return last_modified + ASSET_REVISION
