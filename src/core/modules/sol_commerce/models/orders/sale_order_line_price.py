from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE
from odoo.addons.sol_commerce.constants.orders import STATUS_DRAFT

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLinePriceBase
else:
    SaleOrderLinePriceBase = object


# Dòng Đơn Hàng: a catalog line takes the price in force on its pricing day of its parameter, or for a package of the
# parameters the line holds.
class SaleOrderLinePrice(models.Model, SaleOrderLinePriceBase):
    _inherit = MODEL_SALE_ORDER_LINE

    def _get_display_price(self):
        if self._catalog_lines():
            return self._catalog_price()
        return super()._get_display_price()

    def _lock_catalog_price(self, skip_unpriced=False):
        """Give the open catalog lines the price of their pricing day. Skip_unpriced leaves a line whose item has no
        price that day as it is, for a refresh after a price change; otherwise the line is refused."""
        for line in self._catalog_lines() - self._frozen_lines():
            try:
                price = line._catalog_price()
            except UserError:
                if skip_unpriced:
                    continue
                raise
            # A price that differs from technical_price_unit is kept when the quantity changes.
            line.write({"price_unit": price, "technical_price_unit": 0.0 if price else 1.0})

    def _catalog_price(self):
        """The price of one unit of the line on its pricing day."""
        self.ensure_one()
        template = self.product_id.product_tmpl_id.sudo()
        if template.service_package_id:
            return template.service_package_id._price_on(self._price_date(), self._package_parameters())
        return template.parameter_id.with_context(active_test=False).price_ids[:1]._price_on(self._price_date())

    def _package_parameters(self):
        """The parameters one unit of a package line tests, with how many times: the package's quantity, or once for
        a parameter the customer added; None while the line has no parameter lines yet, so the package's own count."""
        self.ensure_one()
        if not self.linked_line_ids:
            return None
        included = {item.parameter_id: item.quantity for item in self._package_of().line_ids}
        parameters = self._package_parameter_ids()
        return {parameter: included.get(parameter, 1) for parameter in parameters}

    def _price_date(self):
        """Today for the customer's cart, which shows today's catalog; otherwise the quotation date."""
        if self.order_id.order_status == STATUS_DRAFT:
            return fields.Date.context_today(self)
        return self._quotation_date()
