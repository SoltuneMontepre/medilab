from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_BASE_MODULE_UNINSTALL
from odoo.addons.sol_commerce.constants.xml_ids import MODULE
from odoo.addons.sol_laboratory.constants.xml_ids import MODULE as LABORATORY_MODULE

if TYPE_CHECKING:
    from medilab_model_types import Model_base_module_uninstall as BaseModuleUninstallBase
else:
    BaseModuleUninstallBase = object


# Gỡ Cài Đặt Module: warns that uninstalling E-commerce unlinks test requests from their orders.
class BaseModuleUninstall(models.TransientModel, BaseModuleUninstallBase):
    _inherit = MODEL_BASE_MODULE_UNINSTALL

    if not TYPE_CHECKING:
        # True when the uninstall removes E-commerce and keeps Laboratory, whose test requests lose their orders.
        commerce_warning = fields.Boolean(compute="_compute_commerce_warning")

    @api.depends("module_ids")
    def _compute_commerce_warning(self):
        for wizard in self:
            names = set(wizard._get_modules().mapped("name"))
            wizard.commerce_warning = MODULE in names and LABORATORY_MODULE not in names
