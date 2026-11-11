import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .location_case import FLOOR_PLAN, LocationCase
from .people_case import PeopleCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LOCATION,
    MODEL_MACHINE,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)


@tagged("post_install", "-at_install")
class TestLocations(RequestCase, PeopleCase, LocationCase):
    def test_a_location_is_saved_under_a_parent_with_or_without_a_department_and_an_image(self):
        bench = self.create_location("A101-B1", "Bench 1", self.room, department_id=self.chemistry.id)

        self.assertEqual((bench.parent_id, bench.department_id, bench.is_bookable), (self.room, self.chemistry, False))
        self.assertFalse(bench.image_attachment_id)
        self.assertTrue(self.room.is_bookable)
        self.assertFalse(self.room.department_id)
        self.assertEqual(bytes(self.floor.image_attachment_id.raw), base64.b64decode(FLOOR_PLAN))
        self.assertEqual(
            self.env[MODEL_LOCATION].search([("id", "child_of", self.building.id)]),
            self.building | self.floor | self.room | self.other_room | self.sampling_point | bench,
        )

    def test_a_new_image_replaces_the_old_attachment(self):
        old = self.floor.image_attachment_id

        self.floor.image = base64.b64encode(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"/>'
        ).decode()

        self.assertFalse(old.exists())
        self.assertEqual(bytes(self.floor.image), bytes(self.floor.image_attachment_id.raw))
        self.floor.image = False
        self.assertFalse(self.floor.image_attachment_id)

    def test_a_location_placed_on_its_parents_image_shows_as_a_point_on_the_parents_map(self):
        floor_map = self.floor.get_map()

        self.assertEqual(floor_map["image_id"], self.floor.image_attachment_id.id)
        self.assertEqual(
            floor_map["points"],
            [
                {
                    "id": self.sampling_point.id,
                    "code": "A-RO1",
                    "name": "A-RO1 RO water sampling point 1",
                    "x": 0.2,
                    "y": 0.7,
                }
            ],
        )
        self.room.write({"map_x": 0.5, "map_y": 0.1})
        self.assertCountEqual(
            [point["id"] for point in self.floor.get_map()["points"]], [self.room.id, self.sampling_point.id]
        )
        self.assertEqual(
            self.building.get_map(),
            {"name": "KA Main building", "image_id": False, "points": []},
        )

    def test_a_point_lies_on_the_image(self):
        for value in (-0.1, 1.5):
            with self.subTest(value=value):
                message = self.refused_message(lambda value=value: self.room.write({"map_x": value, "map_y": 0.5}))
                self.assertIn("between 0 and 1", message)

    def test_a_location_cannot_be_its_own_ancestor(self):
        for parent in (self.building, self.floor, self.room):
            with self.subTest(parent=parent.code), self.assertRaises(UserError):
                self.building.parent_id = parent

    def test_two_locations_cannot_share_a_code(self):
        message = self.refused_message(lambda: self.create_location("A-RO1", "Another sampling point", self.floor))

        self.assertEqual(message, "The code of a location must be unique.")

    def referrers(self):
        """Each kind of record that names a location, finished or archived so it no longer uses it."""
        retired = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6194:1996", "name": "Chloride by titration", "field_id": self.testing_field.id}
        )
        last_week = fields.Datetime.now() - timedelta(days=7)

        def step(location):
            created = self.env[MODEL_TESTING_METHOD_STEP].create(
                {"method_id": retired.id, "sequence": 1, "duration_minutes": 10, "instruction": "Titrate."}
            )
            created.location_id = location
            retired.action_archive()
            return created

        def sample(location):
            created = self.create_request().sample_ids
            created.write({"sampling_location_id": location.id, "status": "cancelled"})
            return created

        return {
            "location inside it": lambda location: self.create_location(
                f"{location.code}-B1", "Bench 1", location, active=False
            ),
            "machine": lambda location: self.env[MODEL_MACHINE].create(
                {"code": f"AAS-{location.code}", "name": "AAS", "location_id": location.id, "active": False}
            ),
            "step": step,
            "sample": sample,
            "booking": lambda location: self.book(location, last_week),
        }

    def test_a_location_another_record_refers_to_cannot_be_deleted_only_archived(self):
        for number, (kind, refer) in enumerate(self.referrers().items()):
            location = self.create_location(f"P30{number}", f"Room {number}", self.floor, is_bookable=True)
            referrer = refer(location)
            with self.subTest(kind=kind):
                with self.assertRaises(UserError) as refusal:
                    location.unlink()
                self.assertIn(referrer.display_name, str(refusal.exception))
                location.action_archive()
                self.assertFalse(location.active)

    def test_a_location_in_use_cannot_be_archived(self):
        machine = self.env[MODEL_MACHINE].create({"code": "AAS-7", "name": "AAS 7", "location_id": self.room.id})
        tomorrow = fields.Datetime.now() + timedelta(days=1)
        booking = self.book(self.other_room, tomorrow, name="Audit opening")

        for location, user in ((self.room, machine), (self.other_room, booking)):
            with self.subTest(location=location.code), self.assertRaises(UserError) as refusal:
                location.action_archive()
            self.assertIn(user.display_name, str(refusal.exception))

    def test_a_location_nothing_refers_to_can_be_deleted(self):
        bench = self.create_location("A101-B2", "Bench 1", self.room)

        bench.unlink()

        self.assertFalse(bench.exists())

    def test_only_administrators_manage_locations_and_everyone_reads_them(self):
        locations = self.as_person(self.env[MODEL_LOCATION], self.chemist)
        room = self.as_person(self.room, self.chemist)

        self.assertEqual(room.read(["code", "name"])[0]["name"], "Meeting room 1")
        for name, change in {
            "create": lambda: locations.create({"code": "P999", "name": "Store room"}),
            "write": lambda: room.write({"name": "Board room"}),
            "archive": room.action_archive,
            "unlink": room.unlink,
        }.items():
            with self.subTest(change=name), self.assertRaises(AccessError):
                change()

        administrator = self.env.ref("base.user_admin")
        created = self.env[MODEL_LOCATION].with_user(administrator).create({"code": "P999", "name": "Store room"})
        created.write({"parent_id": self.floor.id, "map_x": 0.9, "map_y": 0.9, "is_bookable": True})
        created.action_archive()
        created.unlink()
        self.assertFalse(created.exists())
