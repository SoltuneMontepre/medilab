from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .assertions import assert_instance
from .common import MasterDataCase
from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_SERVICE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestSampleTypeApplicability(MasterDataCase):
    """Lead is tested in-house by AAS and ICP-MS; Cabbage and Lettuce are narrower types of Vegetables."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sample_types = cls.env[MODEL_SAMPLE_TYPE]
        cls.vegetables = sample_types.create({"name": "Vegetables"})
        cls.cabbage = sample_types.create({"name": "Cabbage", "parent_id": cls.vegetables.id})
        cls.lettuce = sample_types.create({"name": "Lettuce", "parent_id": cls.vegetables.id})
        cls.water = sample_types.create({"name": "Bottled water"})
        cls.micrograms = cls.env[MODEL_MEASUREMENT_UNIT].create({"name": "µg/L", "category_id": cls.category.id})
        icp_ms = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "ISO 17294-2:2016", "name": "ICP-MS", "field_id": cls.testing_field.id}
        )
        cls.icp_ms = cls.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": cls.parameter.id, "method_id": icp_ms.id, "department_id": cls.department.id}
        )

    def test_a_narrower_type_without_its_own_applicability_is_not_offered(self):
        self.offer(self.parameter, self.cabbage)

        self.assertEqual(self.parameter.sample_type_ids, self.cabbage)
        self.assertEqual(self.parameter._default_way(self.cabbage), self.pair)
        for sample_type in (self.lettuce, self.vegetables):
            self.assertFalse(self.parameter._default_way(sample_type))
            self.assertIn("is not offered on", assert_instance(self.parameter._order_refusal(sample_type), str))

    def test_one_way_applies_to_two_sample_types_in_different_units(self):
        cabbage = self.offer(self.parameter, self.cabbage, self.icp_ms)
        water = self.offer(self.parameter, self.water, self.icp_ms, unit_id=self.micrograms.id)

        self.assertEqual(self.icp_ms._applicability(self.cabbage), cabbage)
        self.assertEqual(self.icp_ms._applicability(self.cabbage).unit_id, self.unit)
        self.assertEqual(self.icp_ms._applicability(self.water), water)
        self.assertEqual(self.icp_ms._applicability(self.water).unit_id, self.micrograms)

    def test_absent_zero_and_invalid_detection_limits_are_told_apart(self):
        absent = self.offer(self.parameter, self.cabbage)
        zero = self.offer(self.parameter, self.water, lod=0.0, loq=0.0)

        self.assertIs(absent.lod, False)
        self.assertEqual(zero.lod, 0.0)
        self.assertIsNot(zero.lod, False)
        self.env.cr.execute(
            "SELECT id, lod FROM medilab_parameter_method_sample_type WHERE id IN %s", [(absent.id, zero.id)]
        )
        self.assertEqual(dict(self.env.cr.fetchall()), {absent.id: None, zero.id: 0})
        for values in ({"lod": -0.1}, {"loq": -1}, {"lod": 0.3, "loq": 0.1}):
            with self.subTest(values=values), self.assertRaises(ValidationError), self.env.cr.savepoint():
                absent.write(values)
        absent.write({"lod": 0.1})
        self.assertIs(absent.loq, False)

    def test_a_new_default_replaces_the_previous_one_of_its_sample_type_only(self):
        aas_cabbage = self.offer(self.parameter, self.cabbage)
        aas_water = self.offer(self.parameter, self.water)
        icp_cabbage = self.offer(self.parameter, self.cabbage, self.icp_ms)

        icp_cabbage.is_default = True

        self.assertFalse(aas_cabbage.is_default)
        self.assertTrue(aas_water.is_default)
        self.assertEqual(self.parameter._default_way(self.cabbage), self.icp_ms)
        self.assertEqual(self.parameter._default_way(self.water), self.pair)

    def test_a_default_moved_to_another_sample_type_replaces_the_default_there(self):
        water = self.offer(self.parameter, self.water)
        moved = self.offer(self.parameter, self.cabbage, self.icp_ms)

        moved.sample_type_id = self.water

        self.assertFalse(water.is_default)
        self.assertTrue(moved.is_default)
        self.assertEqual(self.parameter._default_way(self.water), self.icp_ms)
        self.assertFalse(self.parameter._default_way(self.cabbage))

    def test_an_unused_sample_type_of_a_way_changes_its_unit(self):
        applicability = self.offer(self.parameter, self.water)

        applicability.unit_id = self.micrograms

        self.assertEqual(applicability.unit_id, self.micrograms)

    def test_a_client_cannot_skip_the_default_checks_through_the_context(self):
        default = self.offer(self.parameter, self.cabbage)
        self.offer(self.parameter, self.cabbage, self.icp_ms)

        with self.assertRaisesRegex(UserError, "before archiving the default"), self.env.cr.savepoint():
            self.pair.with_context(medilab_defaults_checked_by_parameter=True).action_archive()
        with self.assertRaisesRegex(ValidationError, "Choose one default way of testing"), self.env.cr.savepoint():
            default.with_context(medilab_defaults_checked_by_parameter=True).is_default = False

    def test_two_defaults_at_once_are_refused(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.parameter.write(
                {
                    "applicability_ids": [
                        (
                            0,
                            0,
                            {
                                "parameter_method_id": way.id,
                                "sample_type_id": self.cabbage.id,
                                "unit_id": self.unit.id,
                                "is_default": True,
                            },
                        )
                        for way in self.pair | self.icp_ms
                    ]
                }
            )

    def test_an_offered_sample_type_keeps_exactly_one_default(self):
        default = self.offer(self.parameter, self.cabbage)
        other = self.offer(self.parameter, self.cabbage, self.icp_ms)

        with self.assertRaisesRegex(ValidationError, "Choose one default way of testing"), self.env.cr.savepoint():
            default.is_default = False
        with self.assertRaisesRegex(ValidationError, "Choose one default way of testing"), self.env.cr.savepoint():
            default.unlink()
        # Saved together on the parameter form, the default may move to another way in one save.
        self.parameter.write(
            {"applicability_ids": [(1, default.id, {"is_default": False}), (1, other.id, {"is_default": True})]}
        )
        self.assertEqual(self.parameter._default_way(self.cabbage), self.icp_ms)

    def test_archiving_a_default_needs_a_replacement_first(self):
        default = self.offer(self.parameter, self.cabbage)
        replacement = self.offer(self.parameter, self.cabbage, self.icp_ms)

        with self.assertRaisesRegex(UserError, "before archiving the default"), self.env.cr.savepoint():
            self.pair.action_archive()
        replacement.is_default = True
        self.pair.action_archive()

        self.assertFalse(self.pair.active)
        self.assertFalse(default.is_default)
        self.assertEqual(self.parameter._default_way(self.cabbage), self.icp_ms)

    def test_the_parameter_form_moves_the_default_and_archives_the_old_way_in_one_save(self):
        default = self.offer(self.parameter, self.cabbage)
        replacement = self.offer(self.parameter, self.cabbage, self.icp_ms)

        with self.assertRaisesRegex(UserError, "before archiving the default"), self.env.cr.savepoint():
            self.parameter.write({"method_ids": [(1, self.pair.id, {"active": False})]})
        self.parameter.write(
            {
                "method_ids": [(1, self.pair.id, {"active": False})],
                "applicability_ids": [
                    (1, default.id, {"is_default": False}),
                    (1, replacement.id, {"is_default": True}),
                ],
            }
        )

        self.assertFalse(self.pair.active)
        self.assertEqual(self.parameter._default_way(self.cabbage), self.icp_ms)

    def test_restoring_a_way_never_makes_it_the_default(self):
        self.offer(self.parameter, self.cabbage)
        self.offer(self.parameter, self.cabbage, self.icp_ms, is_default=True)
        self.pair.action_archive()

        self.pair.action_unarchive()

        self.assertEqual(self.parameter._default_way(self.cabbage), self.icp_ms)
        self.assertEqual(len(self.parameter.applicability_ids.filtered("is_default")), 1)

    def test_restoring_the_only_way_of_a_sample_type_needs_a_default(self):
        self.offer(self.parameter, self.lettuce, self.icp_ms)
        replacement = self.offer(self.parameter, self.lettuce)
        replacement.is_default = True
        self.icp_ms.action_archive()
        replacement.unlink()
        self.assertFalse(self.parameter.sample_type_ids)

        with self.assertRaisesRegex(ValidationError, "Choose one default way of testing"), self.env.cr.savepoint():
            self.icp_ms.action_unarchive()

    def test_an_unavailable_default_is_explained_and_never_replaced(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create(
            {"name": "Northern Testing Laboratory", "accreditation_expiry": fields.Date.today() + timedelta(days=30)}
        )
        outside = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": self.method.id, "subcontractor_id": subcontractor.id}
        )
        self.offer(self.parameter, self.cabbage, outside)
        self.offer(self.parameter, self.cabbage, self.icp_ms)
        subcontractor.accreditation_expiry = fields.Date.today() - timedelta(days=1)

        notice = assert_instance(self.parameter._default_way_notice(self.cabbage), str)
        self.assertIn("is unavailable", notice)
        self.assertIn("The accreditation of Northern Testing Laboratory expired", notice)
        self.assertIn(self.icp_ms.display_name, notice)
        self.assertFalse(self.parameter._order_refusal(self.cabbage))
        self.assertEqual(self.parameter._default_way(self.cabbage), outside)

        self.icp_ms.applicability_ids.unlink()
        self.assertIn("no other way is", assert_instance(self.parameter._order_refusal(self.cabbage), str))

    def test_a_machine_way_without_a_fit_machine_is_unavailable(self):
        machine = self.env[MODEL_MACHINE].create({"code": "AAS-1", "name": "AAS 1"})
        self.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            {"parameter_method_id": self.pair.id, "machine_id": machine.id, "run_minutes": 30}
        )
        self.assertFalse(self.pair._unavailable_reason())

        self.env[MODEL_MACHINE_SERVICE].create(
            {
                "machine_id": machine.id,
                "kind": "calibration",
                "service_date": fields.Date.today() - timedelta(days=400),
                "next_due_date": fields.Date.today() - timedelta(days=1),
            }
        )

        self.assertIn("No machine that runs it", assert_instance(self.pair._unavailable_reason(), str))


@tagged("post_install", "-at_install")
class TestResultSnapshotOfApplicability(ResultCase):
    def test_a_result_copies_the_unit_and_decimals_of_its_sample_type(self):
        result = self.enter()

        self.assertEqual(result.unit_id, self.unit)
        self.assertEqual(result.value_decimals, 3)

    def test_catalog_edits_leave_entered_results_unchanged_and_the_unit_is_locked(self):
        result = self.enter()
        other_unit = self.env[MODEL_MEASUREMENT_UNIT].create({"name": "mg/kg", "category_id": self.category.id})

        with self.assertRaisesRegex(UserError, "are locked"), self.env.cr.savepoint():
            self.applicability.unit_id = other_unit
        self.applicability.write({"result_decimals": 1, "lod": 0.5})
        result.invalidate_recordset()

        self.assertEqual(result.unit_id, self.unit)
        self.assertEqual(result.value_decimals, 3)

    def test_a_test_refuses_a_way_that_does_not_apply_to_its_sample_type(self):
        method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6193:1996", "name": "Flame AAS", "field_id": self.testing_field.id}
        )
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": method.id, "department_id": self.department.id}
        )

        with self.assertRaisesRegex(ValidationError, "does not apply to"), self.env.cr.savepoint():
            self.test.parameter_method_id = way
        self.offer(self.parameter, self.sample_type, way)
        self.test.parameter_method_id = way

        self.assertEqual(self.test.parameter_method_id, way)
