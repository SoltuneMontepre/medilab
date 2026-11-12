from ast import literal_eval

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_STOCK_CORRECTION,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_QUANT,
    MODEL_STOCK_RELOCATION,
)

# What the storekeeper is given to keep the stores: moving, correcting and disposing of stock, and seeing its value.
KEEPING_PERMISSIONS = ("move.create.all", "stock.read.all")


class StockCase(ContainersCase):
    """The storekeeper keeps the central store and the stores under it; a Bench is a location of the Pesticide
    residues store."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant_inventory(cls.storekeeper, *KEEPING_PERMISSIONS)
        cls.bench = cls.env[MODEL_STOCK_LOCATION].create({"name": "Bench", "location_id": cls.pesticides_store.id})
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")

    def receive(self, item, quantity, price, location=None, lot=None, container=None):
        """A valued incoming move of quantity of the item at this unit price, into the central store by default."""
        moves = self.env[MODEL_STOCK_MOVE]
        take = {"quantity": quantity, "lot": lot, "result_package": container}
        return moves._done_move(item, self.supplier_location, location or self.central, [take], price_unit=price)

    def relocate(self, user, **vals):
        return self.env[MODEL_STOCK_RELOCATION].with_user(user).create(vals).action_confirm()

    def correct(self, user, **vals):
        return self.env[MODEL_STOCK_CORRECTION].with_user(user).create(vals).action_confirm()

    def listed(self, user, action):
        """The stock this screen lists for the user."""
        return self.env[MODEL_STOCK_QUANT].with_user(user).search(literal_eval(self.env.ref(action).domain))

    def held(self, item, location):
        """The quantity of the item at this location and the locations inside it."""
        return item.with_context(location=location.id).qty_available
