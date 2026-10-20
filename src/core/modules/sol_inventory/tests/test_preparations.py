from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_PREPARATION_MAKE,
    MODEL_RECIPE,
    MODEL_STOCK_LOT,
)
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
    CONTAINER_OPENED,
    MOVE_PREPARATION,
    MOVE_WASTE,
)
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SCRAP_OTHER, SCRAP_WRONGLY_PREPARED


@tagged("post_install", "-at_install")
class TestPreparations(ContainersCase):
    def prepare(
        self, acid_quantity=77, water_quantity=923, received=1000, acid=None, water=None, tags=None, extra_reason=False
    ):
        mark = self.env[MODEL_STOCK_LOT].search_count([])
        acid = acid or self.put_container(self.acid, 500, f"Acid{mark}", status=CONTAINER_OPENED)
        water = water or self.put_container(self.water, 1000, f"Water{mark}", status=CONTAINER_OPENED)
        wizard = (
            self.env[MODEL_PREPARATION_MAKE]
            .with_user(self.tester.user_id)
            .create(
                {
                    "recipe_id": self.recipe.id,
                    "location_id": self.pesticides_store.id,
                    "received_quantity": received,
                    "scrap_reason_tag_ids": [Command.set(tags.ids)] if tags else False,
                    "extra_reason": extra_reason,
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
        self.assertEqual(set(preparation.move_ids.mapped("reference")), {container.lot_id.name})
        self.assertTrue(self.dilute_acid.use_expiration_date)
        html = self.env["ir.actions.report"]._render_qweb_html(CONTAINER_LABEL_REPORT, container.ids)[0].decode()
        self.assertIn("Prepared", html)
        self.assertIn(self.tester.name, html)

    def test_a_scan_on_the_dialog_joins_the_line_of_its_ingredient(self):
        acid = self.put_container(self.acid, 500, "ScanA", status=CONTAINER_OPENED)
        water = self.put_container(self.water, 1000, "ScanW", status=CONTAINER_OPENED)
        other = self.put_container(self.rinse, 100, "ScanR", status=CONTAINER_OPENED)
        wizard = (
            self.env[MODEL_PREPARATION_MAKE]
            .with_user(self.tester.user_id)
            .create({"recipe_id": self.recipe.id, "location_id": self.pesticides_store.id})
        )
        wizard._onchange_recipe_id()

        for code in (f" {water.name} ", acid.name):
            wizard.container_scan = code
            wizard._onchange_container_scan()

        acid_line = wizard.line_ids.filtered(lambda line: line.item_id == self.acid)
        water_line = wizard.line_ids.filtered(lambda line: line.item_id == self.water)
        self.assertEqual(acid_line.container_ids.container_id, acid)
        self.assertEqual(water_line.container_ids.container_id, water)
        self.assertFalse(wizard.container_scan)
        for code, message in ((acid.name, "already on this preparation"), (other.name, "does not use")):
            wizard.container_scan = code
            with self.assertRaises(UserError) as refused:
                wizard._onchange_container_scan()
            self.assertIn(message, refused.exception.args[0])

        wizard.action_prepare()

        self.assertEqual(acid.quantity, 423)
        self.assertEqual(water.quantity, 77)

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
        with self.assertRaises(UserError) as too_much:
            self.prepare(received=1001)
        self.assertIn("recipe yield", too_much.exception.args[0])
        with self.assertRaises(UserError) as extra:
            self.prepare(acid_quantity=80)
        self.assertIn("reason for the extra", extra.exception.args[0])

    def test_extra_wasted_for_another_reason_says_what_happened(self):
        other = self.env.ref(SCRAP_OTHER)
        with self.assertRaises(UserError) as unsaid:
            self.prepare(acid_quantity=80, tags=other)
        self.assertIn("Other", unsaid.exception.args[0])

        preparation, _acid, _water = self.prepare(acid_quantity=80, tags=other, extra_reason="Pipette overshot")

        waste = preparation.move_ids.filtered(lambda move: move.is_scrap)
        self.assertEqual((waste.reason, waste.scrap_reason_tag_ids), ("Pipette overshot", other))

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

    def batch(self, lines, received=1000, location=None, tags=None, recipe=None):
        return (
            self.env[MODEL_PREPARATION]
            .with_user(self.tester.user_id)
            .prepare(
                self.recipe if recipe is None else recipe,
                location or self.pesticides_store,
                lines,
                received,
                tags or self.env["stock.scrap.reason.tag"],
            )
        )

    def test_a_batch_that_does_not_follow_the_recipe_is_refused(self):
        acid = self.put_container(self.acid, 500, "Follow", status=CONTAINER_OPENED)
        water = self.put_container(self.water, 1000, "FollowW", status=CONTAINER_OPENED)
        lines = [
            {"item": self.acid, "quantity": 77, "containers": acid},
            {"item": self.water, "quantity": 923, "containers": water},
        ]
        refusals = (
            (self.env[MODEL_RECIPE].browse(), lines, 1000, "Choose a recipe."),
            (self.recipe, lines, 0, "above zero"),
            (self.recipe, [{"item": self.acid, "quantity": 10, "containers": acid}], 1000, "less than the recipe"),
            (
                self.recipe,
                [{"item": self.gloves, "quantity": 1, "containers": self.env["stock.package"]}],
                1000,
                "not an ingredient",
            ),
            (
                self.recipe,
                [
                    {"item": self.acid, "quantity": 77, "containers": acid},
                    {"item": self.acid, "quantity": 77, "containers": acid},
                ],
                1000,
                "already on this preparation",
            ),
            (self.recipe, [lines[0]], 1000, "Prepare every ingredient"),
        )
        for recipe, ingredient_lines, received, message in refusals:
            with self.subTest(message=message), self.assertRaises(UserError) as refusal:
                self.batch(ingredient_lines, received=received, recipe=recipe)
            self.assertIn(message, refusal.exception.args[0])

        self.recipe.active = False
        with self.assertRaises(UserError) as inactive:
            self.batch(lines)
        self.assertIn("Choose a recipe.", inactive.exception.args[0])

    def test_the_rest_of_a_later_container_is_wasted(self):
        first = self.put_container(self.acid, 77, "Recipe", status=CONTAINER_OPENED)
        rest = self.put_container(self.acid, 10, "Extra", status=CONTAINER_OPENED)
        water = self.put_container(self.water, 1000, "RestW", status=CONTAINER_OPENED)

        preparation, _container = self.batch(
            [
                {"item": self.acid, "quantity": 87, "containers": first | rest},
                {"item": self.water, "quantity": 923, "containers": water},
            ],
            tags=self.env.ref(SCRAP_WRONGLY_PREPARED),
        )

        waste = preparation.move_ids.filtered("is_scrap")
        self.assertEqual(waste.product_id, self.acid)
        self.assertEqual(waste.quantity, 10)
        self.assertEqual(first.quantity, 0)
        self.assertEqual(first.status, CONTAINER_DEPLETED)
        self.assertEqual(rest.quantity, 0)
        self.assertEqual(rest.status, CONTAINER_DISPOSED)

    def test_preparing_outside_the_persons_store_or_without_the_sequence_is_refused(self):
        acid = self.put_container(self.acid, 500, "Place", status=CONTAINER_OPENED)
        water = self.put_container(self.water, 1000, "PlaceW", status=CONTAINER_OPENED)
        lines = [
            {"item": self.acid, "quantity": 77, "containers": acid},
            {"item": self.water, "quantity": 923, "containers": water},
        ]
        with self.assertRaises(UserError) as store:
            self.batch(lines, location=self.chemistry_store)
        self.assertIn("your stores", store.exception.args[0])

        second = self.create_store("Second pesticide store", self.chemistry_store, self.pesticides)
        elsewhere = self.put_container(self.acid, 500, "Elsewhere", location=second, status=CONTAINER_OPENED)
        with self.assertRaises(UserError) as outside:
            self.batch(
                [
                    {"item": self.acid, "quantity": 77, "containers": elsewhere},
                    {"item": self.water, "quantity": 923, "containers": water},
                ]
            )
        self.assertIn(elsewhere.name, outside.exception.args[0])

        clerk = self.create_person("Le Thi Pha", self.chemistry, "pha.le")
        clerk.team_id = self.pesticides
        with self.assertRaises(AccessError):
            self.env[MODEL_PREPARATION].with_user(clerk.user_id).prepare(
                self.recipe, self.pesticides_store, lines, 1000, self.env["stock.scrap.reason.tag"]
            )

        self.env["ir.sequence"].search([("code", "=", "medilab.preparation.lot")]).code = "medilab.preparation.lot.away"
        with self.assertRaises(UserError) as missing:
            self.prepare()
        self.assertIn("sequence", missing.exception.args[0])
