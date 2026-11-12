from datetime import timedelta

from odoo import fields

from .recipe_case import RecipeCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_PACKAGE, MODEL_STOCK_QUANT
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED, CONTAINER_SEALED

# What a tester is given to open containers, prepare solutions and record use or waste.
CONTAINER_PERMISSIONS = ("container.edit.all", "preparation.create.all", "move.create.all")


class ContainersCase(RecipeCase):
    """A tester of the Pesticide residues team, and containers put straight into that team's store."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.tz = "UTC"
        cls.tester = cls.create_person("Mai Thi Thu", cls.chemistry, "thu.mai")
        cls.tester.team_id = cls.pesticides
        cls.grant_inventory(cls.tester, *CONTAINER_PERMISSIONS)
        cls.acid.use_expiration_date = True
        cls.water.use_expiration_date = True
        (cls.acid | cls.water).write({"use_shelf_life_after_opening": True, "shelf_life_after_opening_days": 30})
        cls.acid.standard_price = 2
        cls.water.standard_price = 1

    def put_container(self, item, quantity, lot_name, expiration=None, location=None, status=CONTAINER_SEALED):
        """A container of item holding quantity, in the tester's store unless a location is given."""
        packages = self.env[MODEL_STOCK_PACKAGE]
        lot = self.env[MODEL_STOCK_LOT].create(
            {
                "name": lot_name,
                "product_id": item.id,
                "company_id": self.env.company.id,
                "expiration_date": expiration if expiration is not None else packages._at_utc(self.day(30)),
            }
        )
        container = packages.create({"name": f"{lot_name}-01", "status": status})
        self.env[MODEL_STOCK_QUANT]._update_available_quantity(
            item, location or self.pesticides_store, quantity, lot_id=lot, package_id=container
        )
        if status == CONTAINER_OPENED:
            container.write(
                {"opened_at": fields.Datetime.now(), "opened_by_id": self.tester.user_id.id, "status": status}
            )
        return container

    def day(self, offset):
        return self.env[MODEL_STOCK_PACKAGE]._today() + timedelta(days=offset)

    def as_tester(self, records):
        return self.as_person(records, self.tester)
