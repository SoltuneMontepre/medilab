from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import MODEL_CONTAINER_OPENING, MODEL_STOCK_PACKAGE
from odoo.addons.sol_inventory.constants.stock import CONTAINER_DISPOSED, CONTAINER_OPENED, CONTAINER_SEALED
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_EXPIRED

NOTE = "Opened on the bench without a scan"


@tagged("post_install", "-at_install")
class TestRecordedOpenings(ContainersCase):
    """The storekeeper of the central store records an opening the tester could not make."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant_inventory(cls.storekeeper, "container.edit.all")

    def record(self, container, person=None, opened_at=None, note=NOTE):
        wizard = (
            self.env[MODEL_CONTAINER_OPENING]
            .with_user((person or self.storekeeper).user_id)
            .with_context(default_container_id=container.id)
            .create(
                {
                    "opened_by_id": self.tester.user_id.id,
                    "opened_at": opened_at or fields.Datetime.now(),
                    "note": note,
                }
            )
        )
        return wizard.action_confirm()

    def test_the_storekeeper_records_who_opened_a_container_when_and_why(self):
        self.put_container(self.acid, 500, "Already", status=CONTAINER_OPENED)
        container = self.put_container(self.acid, 500, "Recorded")
        yesterday = fields.Datetime.now() - timedelta(days=1)

        action = self.record(container, opened_at=yesterday)

        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual((container.opened_by_id, container.opened_at), (self.tester.user_id, yesterday))
        self.assertEqual(container.opening_note, NOTE)
        # Opened yesterday with 30 days after opening, before the lot expires in 30 days.
        self.assertEqual(container.usable_until, self.day(29))
        self.assertEqual(action["type"], "ir.actions.report")

    def test_a_container_past_its_usable_date_is_disposed_of_as_expired(self):
        container = self.put_container(self.acid, 500, "Spoiled", self.env[MODEL_STOCK_PACKAGE]._at_utc(self.day(-2)))

        self.record(container)

        move = container.done_line_ids.move_id
        self.assertEqual((container.status, container.quantity), (CONTAINER_DISPOSED, 0))
        self.assertEqual(container.opened_by_id, self.tester.user_id)
        self.assertTrue(move.is_scrap)
        self.assertEqual(move.scrap_reason_tag_ids, self.env.ref(SCRAP_EXPIRED))

    def test_an_opening_older_than_the_shelf_life_after_opening_is_disposed_of(self):
        container = self.put_container(self.acid, 500, "Forgotten")

        self.record(container, opened_at=fields.Datetime.now() - timedelta(days=40))

        self.assertEqual(container.status, CONTAINER_DISPOSED)

    def test_only_the_storekeeper_of_its_store_records_a_complete_opening(self):
        container = self.put_container(self.acid, 500, "Guarded")
        with self.assertRaises(UserError):
            self.record(container, person=self.tester)
        with self.assertRaises(AccessError):
            self.record(container, person=self.chemist)
        with self.assertRaises(UserError):
            self.record(container, note=" ")
        with self.assertRaises(UserError):
            self.record(container, opened_at=fields.Datetime.now() + timedelta(days=1))
        self.assertEqual(container.status, CONTAINER_SEALED)

        self.record(container)

        with self.assertRaises(UserError):
            self.record(container)
