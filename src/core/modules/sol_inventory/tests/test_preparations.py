from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import MODEL_PREPARATION, MODEL_PREPARATION_MAKE
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
    CONTAINER_OPENED,
    MOVE_PREPARATION,
    MOVE_WASTE,
)
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SCRAP_WRONGLY_PREPARED


@tagged("post_install", "-at_install")
class TestPreparations(ContainersCase):
    def prepare(self, acid_quantity=77, water_quantity=923, received=1000, acid=None, water=None, tags=None):
        acid = acid or self.put_container(self.acid, 500, "Acid", status=CONTAINER_OPENED)
        water = water or self.put_container(self.water, 1000, "Water", status=CONTAINER_OPENED)
        wizard = (
            self.env[MODEL_PREPARATION_MAKE]
            .with_user(self.tester.user_id)
            .create(
                {
                    "recipe_id": self.recipe.id,
                    "location_id": self.pesticides_store.id,
                    "received_quantity": received,
                    "scrap_reason_tag_ids": [Command.set(tags.ids)] if tags else False,
                    "line_ids": [
                        Command.create(
                            {
                                "item_id": self.acid.id,
                                "recipe_quantity": 77,
                                "quantity": acid_quantity,
                                "container_ids": [Command.create({"container_id": acid.id, "sequence": 1})],
                            }
                        ),
                        Command.create(
                            {
                                "item_id": self.water.id,
                                "recipe_quantity": 923,
                                "quantity": water_quantity,
                                "container_ids": [Command.create({"container_id": water.id, "sequence": 1})],
                            }
                        ),
                    ],
                }
            )
        )
        wizard.action_prepare()
        return self.env[MODEL_PREPARATION].search([], order="id desc", limit=1), acid, water

    def test_one_batch_fills_a_new_container_and_uses_the_ingredients(self):
        preparation, acid, water = self.prepare()
        container = preparation.container_ids

        self.assertEqual(container.name, f"{container.lot_id.name}-01")
        self.assertTrue(container.lot_id.name.startswith("PC."))
        self.assertEqual(len(container.lot_id.name), 7)
        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(container.item_id, self.dilute_acid)
        self.assertEqual(container.quantity, 1000)
        self.assertEqual(container.location_id, self.pesticides_store)
        self.assertEqual(container.usable_until, self.day(14))
        self.assertEqual(acid.quantity, 423)
        self.assertEqual(water.quantity, 77)
        self.assertEqual(
            preparation.move_ids.filtered(lambda move: move.product_id == self.acid).move_kind, MOVE_PREPARATION
        )
        incoming = preparation.move_ids.filtered(lambda move: move.product_id == self.dilute_acid)
        spent = sum(abs(move.value) for move in preparation.move_ids - incoming)
        self.assertAlmostEqual(incoming.price_unit, spent / 1000, places=4)
        html = self.env["ir.actions.report"]._render_qweb_html(CONTAINER_LABEL_REPORT, container.ids)[0].decode()
        self.assertIn("Prepared", html)
        self.assertIn(self.tester.name, html)

    def test_an_earlier_ingredient_date_limits_the_solution(self):
        acid = self.put_container(
            self.acid,
            500,
            "Soon",
            self.env["stock.package"]._at_utc(self.day(5)),
            status=CONTAINER_OPENED,
        )
        preparation, _acid, _water = self.prepare(acid=acid)

        self.assertEqual(preparation.container_ids.usable_until, self.day(5))

    def test_extra_ingredient_is_wasted_and_the_yield_cannot_grow(self):
        tags = self.env.ref(SCRAP_WRONGLY_PREPARED)
        preparation, acid, _water = self.prepare(acid_quantity=80, tags=tags)
        waste = preparation.move_ids.filtered(lambda move: move.is_scrap)

        self.assertEqual(waste.product_id, self.acid)
        self.assertEqual(waste.quantity, 3)
        self.assertEqual(waste.move_kind, MOVE_WASTE)
        self.assertEqual(waste.scrap_reason_tag_ids, tags)
        self.assertEqual(acid.quantity, 420)
        self.assertNotEqual(acid.status, CONTAINER_DISPOSED)
        with self.assertRaises(UserError):
            self.prepare(received=1001)
        with self.assertRaises(UserError):
            self.prepare(acid_quantity=80)

    def test_a_sealed_expired_short_or_wrong_container_is_refused(self):
        sealed = self.put_container(self.acid, 500, "Sealed")
        expired = self.put_container(
            self.acid, 500, "Old", self.env["stock.package"]._at_utc(self.day(-2)), status=CONTAINER_OPENED
        )
        short = self.put_container(self.acid, 10, "Short", status=CONTAINER_OPENED)
        wrong = self.put_container(self.water, 500, "Wrong", status=CONTAINER_OPENED)
        for kwargs in (
            {"acid": sealed},
            {"acid": expired},
            {"acid": short},
            {"acid": wrong, "acid_quantity": 77},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(UserError):
                self.prepare(**kwargs)
        self.assertEqual(sealed.status, "sealed")
        self.assertNotEqual(short.status, CONTAINER_DEPLETED)
