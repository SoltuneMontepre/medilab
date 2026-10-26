from odoo.exceptions import UserError
from odoo.tests import tagged

from .catalog_case import CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_QUANT
from odoo.addons.sol_laboratory.constants.models import MODEL_LOCATION


@tagged("post_install", "-at_install")
class TestStorePlaces(CatalogCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        places = cls.env[MODEL_LOCATION]
        cls.floor = places.create({"code": "T-F1", "name": "Floor 1"})
        cls.room = places.create({"code": "T-F1-R1", "name": "Room 1", "parent_id": cls.floor.id})
        cls.bench = places.create({"code": "T-F1-R1-B1", "name": "Bench 1", "parent_id": cls.room.id})
        cls.other_floor = places.create({"code": "T-F2", "name": "Floor 2"})
        cls.central.place_id = cls.room
        cls.fridge.place_id = cls.bench

    def stock_at(self, place):
        return self.env[MODEL_STOCK_QUANT].search([("location_id.place_id", "child_of", place.id)]).location_id

    def test_choosing_a_floor_shows_the_stock_of_the_rooms_and_benches_under_it(self):
        self.put_stock(self.gloves, self.central, 10)
        self.put_stock(self.gloves, self.fridge, 5)

        self.assertEqual(self.stock_at(self.floor), self.central | self.fridge)
        self.assertEqual(self.stock_at(self.room), self.central | self.fridge)
        self.assertEqual(self.stock_at(self.bench), self.fridge)
        self.assertFalse(self.stock_at(self.other_floor))

    def test_the_stock_search_by_place_finds_the_stock_under_it(self):
        self.put_stock(self.gloves, self.fridge, 5)
        quants = self.env[MODEL_STOCK_QUANT]
        view = quants.get_view(self.env.ref("stock.quant_search_view").id, "search")

        self.assertIn("location_id.place_id", view["arch"])
        self.assertEqual(quants.search([("location_id.place_id", "child_of", self.floor.id)]).location_id, self.fridge)

    def test_a_stock_location_is_saved_without_a_place(self):
        location = self.env["stock.location"].create({"name": "Shelf 3", "location_id": self.central.id})

        self.assertFalse(location.place_id)

    def test_a_place_a_stock_location_names_cannot_be_deleted_or_archived_while_it_is_active(self):
        with self.assertRaises(UserError) as refusal:
            self.bench.unlink()
        self.assertIn(self.fridge.display_name, str(refusal.exception))
        with self.assertRaises(UserError):
            self.bench.action_archive()

        self.fridge.action_archive()
        self.bench.action_archive()

        self.assertFalse(self.bench.active)
        with self.assertRaises(UserError):
            self.bench.unlink()
