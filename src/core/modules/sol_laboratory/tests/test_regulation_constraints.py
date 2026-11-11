from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import Form, tagged
from odoo.tests.form import O2MProxy
from odoo.tools import mute_logger

from .assertions import assert_instance
from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_REGULATION, MODEL_REGULATION_LIMIT, MODEL_SAMPLE_TYPE


@tagged("post_install", "-at_install")
class TestRegulationConstraints(MasterDataCase):
    """A regulation on vegetables, whose narrower types are cabbage and lettuce, and water outside its scope."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vegetables, cls.water = cls.env[MODEL_SAMPLE_TYPE].create([{"name": "Vegetables"}, {"name": "Water"}])
        cls.cabbage, cls.lettuce = cls.env[MODEL_SAMPLE_TYPE].create(
            [{"name": "Cabbage", "parent_id": cls.vegetables.id}, {"name": "Lettuce", "parent_id": cls.vegetables.id}]
        )
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {"code": "QCVN 8-2:2011/BYT", "name": "Heavy metals in food", "sample_type_ids": cls.vegetables.ids}
        )

    def create_limit(self, sample_type=None, **vals):
        return self.env[MODEL_REGULATION_LIMIT].create(
            {
                "regulation_id": self.regulation.id,
                "parameter_id": self.parameter.id,
                "sample_type_id": (sample_type or self.cabbage).id,
                **vals,
            }
        )

    def test_two_sample_types_have_their_own_limit_for_one_parameter(self):
        cabbage = self.create_limit(max_set=True, max_value=0.3, unit_id=self.unit.id)
        lettuce = self.create_limit(self.lettuce, max_set=True, max_value=0.1, unit_id=self.unit.id)

        self.assertEqual(self.regulation.limit_ids, cabbage | lettuce)
        self.assertEqual((cabbage.max_value, lettuce.max_value), (0.3, 0.1))

    def test_one_limit_per_parameter_and_sample_type(self):
        self.create_limit(max_set=True, max_value=0.01, unit_id=self.unit.id)

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_limit(limit_text="Not detected")

    def test_a_limit_is_only_for_a_sample_type_in_the_scope(self):
        self.create_limit(self.vegetables, limit_text="Not detected")

        with self.assertRaises(ValidationError):
            self.create_limit(self.water, limit_text="Not detected")

    def test_a_sample_type_with_limits_cannot_leave_the_scope(self):
        self.create_limit(limit_text="Not detected")

        with self.assertRaises(ValidationError) as refusal:
            self.regulation.sample_type_ids = self.water

        self.assertIn("Lead (Pb) – Cabbage", str(refusal.exception))
        self.assertEqual(self.regulation.sample_type_ids, self.vegetables)

    def test_limit_needs_a_minimum_a_maximum_or_a_text(self):
        with self.assertRaises(ValidationError):
            self.create_limit(unit_id=self.unit.id)

    def test_numeric_limit_needs_a_unit(self):
        with self.assertRaises(ValidationError):
            self.create_limit(max_set=True, max_value=0.01)

    def test_zero_without_the_flag_is_not_a_limit(self):
        with self.assertRaises(ValidationError):
            self.create_limit(max_value=0, unit_id=self.unit.id)

    def test_zero_is_a_limit_when_it_is_set(self):
        limit = self.create_limit(min_set=True, max_set=True, min_value=0, max_value=0, unit_id=self.unit.id)

        self.assertEqual((limit.min_value, limit.max_value), (0, 0))

    def test_minimum_above_maximum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create_limit(min_set=True, max_set=True, min_value=0, max_value=-1, unit_id=self.unit.id)

    def test_text_limit_needs_no_unit(self):
        limit = self.create_limit(limit_text="Not detected")

        self.assertEqual(self.regulation.limit_ids, limit)

    def test_first_valid_day_after_the_last_is_refused(self):
        with self.assertRaises(ValidationError):
            self.regulation.write({"valid_from": "2026-01-02", "valid_until": "2026-01-01"})

    def test_a_covered_type_offering_a_limited_parameter_without_its_own_limit_is_missing(self):
        self.offer(self.parameter, self.cabbage)
        self.offer(self.parameter, self.lettuce)
        self.offer(self.parameter, self.water)
        self.create_limit(max_set=True, max_value=0.3, unit_id=self.unit.id)

        self.assertEqual(self.regulation.missing_limits, "Lead (Pb) – Lettuce")
        self.create_limit(self.lettuce, max_set=True, max_value=0.3, unit_id=self.unit.id)
        self.assertFalse(self.regulation.missing_limits)


@tagged("post_install", "-at_install")
class TestRegulationRows(MasterDataCase):
    """Cabbage offers lead and cadmium; lead already has a limit on cabbage."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cabbage = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage"})
        cls.cadmium = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.offer(cls.parameter, cls.cabbage)
        cls.offer(cls.cadmium, cls.cabbage)
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {
                "code": "QCVN 8-2:2011/BYT",
                "name": "Heavy metals in food",
                "sample_type_ids": cls.cabbage.ids,
                "limit_ids": [
                    Command.create(
                        {
                            "parameter_id": cls.parameter.id,
                            "sample_type_id": cls.cabbage.id,
                            "max_set": True,
                            "max_value": 0.3,
                            "unit_id": cls.unit.id,
                        }
                    )
                ],
            }
        )

    def add_rows(self, form):
        """Pick cabbage to add its rows, and return the parameter, sample type and unit of each row on the form."""
        form.add_sample_type_ids.add(self.cabbage)
        limits = assert_instance(form.limit_ids, O2MProxy)
        rows = []
        for index in range(len(limits)):
            with limits.edit(index) as row:
                rows.append((row.parameter_id, row.sample_type_id, row.unit_id))
        return rows

    def test_adding_rows_prepares_each_missing_offered_parameter_once_and_keeps_entered_limits(self):
        with Form(self.regulation) as form:
            rows = self.add_rows(form)
            again = self.add_rows(form)
            self.assertEqual(self.regulation.limit_ids.parameter_id, self.parameter, "Nothing is saved before Save.")
            with assert_instance(form.limit_ids, O2MProxy).edit(1) as row:
                row.limit_text = "Not detected"

        expected = [(self.parameter, self.cabbage, self.unit), (self.cadmium, self.cabbage, self.unit)]
        self.assertEqual(rows, expected)
        self.assertEqual(again, expected)
        lead = self.regulation.limit_ids.filtered(lambda limit: limit.parameter_id == self.parameter)
        self.assertEqual(lead.max_value, 0.3)
        self.assertEqual(len(self.regulation.limit_ids), 2)

    def test_a_prepared_row_left_without_a_limit_cannot_be_saved(self):
        form = Form(self.regulation)
        self.add_rows(form)

        with self.assertRaises(ValidationError):
            form.save()
