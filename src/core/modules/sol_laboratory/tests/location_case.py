import base64
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo.tests import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_CALENDAR_EVENT, MODEL_LOCATION

FLOOR_PLAN = base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60"/>').decode()


class LocationCase(TransactionCase):
    """A building whose first floor has a floor plan, with two bookable meeting rooms on it and a sampling point."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = cls.create_location("KA", "Main building")
        cls.floor = cls.create_location("KA-T1", "Floor 1", cls.building, image=FLOOR_PLAN)
        cls.room, cls.other_room = (
            cls.create_location(code, name, cls.floor, is_bookable=True)
            for code, name in (("A101", "Meeting room 1"), ("A102", "Meeting room 2"))
        )
        cls.sampling_point = cls.create_location("A-RO1", "RO water sampling point 1", cls.floor, map_x=0.2, map_y=0.7)

    @classmethod
    def create_location(cls, code, name, parent=None, **vals):
        return cls.env[MODEL_LOCATION].create(
            {"code": code, "name": name, "parent_id": parent.id if parent else False, **vals}
        )

    @classmethod
    def book(cls, location, start, hours=1, user=None, name="Method validation meeting", **vals):
        """A calendar event that books the location, organised by the user."""
        events = cls.env[MODEL_CALENDAR_EVENT].with_user(user) if user else cls.env[MODEL_CALENDAR_EVENT]
        return events.create(
            {"name": name, "location_id": location.id, "start": start, "stop": start + timedelta(hours=hours), **vals}
        )

    def refused_message(self, change, model=MODEL_LOCATION):
        """The message a user gets when a change breaks a database constraint of the model."""
        with self.assertRaises(IntegrityError) as refusal, mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            change()
            self.env.flush_all()
        return self.env[model]._sql_error_to_message(refusal.exception)
