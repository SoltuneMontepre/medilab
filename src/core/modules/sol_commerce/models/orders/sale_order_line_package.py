from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLinePackageBase
else:
    SaleOrderLinePackageBase = object


# Dòng Đơn Hàng: the customer chooses which parameters a package line tests; its price follows them.
class SaleOrderLinePackage(models.Model, SaleOrderLinePackageBase):
    _inherit = MODEL_SALE_ORDER_LINE

    def _package_parameter_ids(self):
        """The parameters the package line tests."""
        self.ensure_one()
        return self.linked_line_ids.product_id.product_tmpl_id.sudo().parameter_id

    def _set_package_parameters(self, parameters):
        """Make the package line test exactly the parameters: drop the others and add the missing ones once per
        package. A package keeps at least one parameter."""
        self.ensure_one()
        if not self._package_of():
            raise UserError(self.env._("Only a package line holds parameters."))
        if not parameters:
            raise UserError(self.env._("A package keeps at least one parameter."))
        dropped = self.linked_line_ids.filtered(
            lambda part: part.product_id.product_tmpl_id.sudo().parameter_id not in parameters
        )
        missing = parameters - self._package_parameter_ids()
        dropped.unlink()
        if missing:
            self.create(self._package_part_vals(dict.fromkeys(missing, 1)))
        self._lock_catalog_price()
        return self
