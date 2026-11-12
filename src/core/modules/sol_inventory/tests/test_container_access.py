from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import MODEL_PREPARATION, MODEL_STOCK_MOVE, MODEL_STOCK_PICKING
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED


@tagged("post_install", "-at_install")
class TestContainerAccess(ContainersCase):
    def test_the_team_store_is_used_and_the_department_store_when_the_team_has_none(self):
        own = self.put_container(self.acid, 100, "Team")
        department = self.put_container(self.acid, 100, "Dept", location=self.chemistry_store)
        self.as_tester(own).action_open()
        with self.assertRaises(UserError):
            self.as_tester(department).action_open()

        self.tester.team_id = False
        self.as_tester(department).action_open()
        self.assertEqual(department.status, CONTAINER_OPENED)

    def test_every_store_one_holder_has_counts(self):
        second = self.create_store("Second pesticide store", self.chemistry_store, self.pesticides)
        self.assertEqual(self.tester._store(), self.pesticides_store | second)
        bottle = self.put_container(self.acid, 100, "Second", location=second)

        self.as_tester(bottle).action_open()

        self.assertEqual(bottle.status, CONTAINER_OPENED)

    def test_a_person_with_no_store_is_told_so(self):
        person = self.create_person("Vo Van Khong", self.microbiology, "khong.vo")

        with self.assertRaises(UserError):
            person._store()

    def test_recording_a_move_cannot_create_a_receipt(self):
        warehouse = self.env.ref("stock.warehouse0")
        picking = self.env[MODEL_STOCK_PICKING].create(
            {
                "picking_type_id": warehouse.in_type_id.id,
                "location_id": warehouse.in_type_id.default_location_src_id.id,
                "location_dest_id": self.central.id,
            }
        )

        with self.assertRaises(AccessError):
            self.env[MODEL_STOCK_MOVE].with_user(self.tester.user_id).create(
                {
                    "product_id": self.gloves.id,
                    "product_uom_qty": 1,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "picking_id": picking.id,
                }
            )

    def test_an_internal_user_reads_a_preparation_and_a_move_that_touches_a_container(self):
        preparation = self.env[MODEL_PREPARATION].create(
            {"recipe_id": self.recipe.id, "location_id": self.pesticides_store.id}
        )
        container = self.put_container(self.acid, 100, "Read", status=CONTAINER_OPENED)
        use = (
            self.env["medilab.stock.use"]
            .with_user(self.tester.user_id)
            .create(
                {
                    "kind": "use",
                    "container_id": container.id,
                    "item_id": container.item_id.id,
                    "quantity": 10,
                    "reason": "Check",
                }
            )
        )
        use.action_confirm()
        move = container.done_line_ids.move_id
        reader = self.create_person("Do Van Doc", self.chemistry, "doc.do")

        self.assertEqual(
            preparation.with_user(reader.user_id).search([("id", "=", preparation.id)]),
            preparation,
        )
        self.assertEqual(move.with_user(reader.user_id).search([("id", "=", move.id)]), move)
