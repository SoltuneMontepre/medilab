from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.laboratory.constants.models import (
    MODEL_CHEMICAL,
    MODEL_MACHINE,
    MODEL_MACHINE_SERVICE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
)


@tagged("post_install", "-at_install")
class TestArchivingAndDeleting(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.machine = cls.env[MODEL_MACHINE].create({"code": "AAS-09", "name": "AAS 9"})
        cls.subcontractor = cls.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"})

    def test_archived_record_is_not_offered_for_selection(self):
        ppt = self.env[MODEL_MEASUREMENT_UNIT].create({"name": "ppt", "category_id": self.category.id})

        ppt.action_archive()

        offered = self.env[MODEL_MEASUREMENT_UNIT].name_search("pp")
        self.assertNotIn(ppt.id, [record_id for record_id, _name in offered])

    def test_unit_of_active_way_of_testing_cannot_be_archived_or_deleted(self):
        for action in (self.unit.action_archive, self.unit.unlink):
            with self.subTest(action=action.__name__), self.assertRaises(UserError) as refusal:
                action()
            self.assertIn(self.pair.display_name, str(refusal.exception))

    def test_unit_can_be_archived_once_its_ways_of_testing_are_archived(self):
        self.pair.action_archive()

        self.unit.action_archive()

        self.assertFalse(self.unit.active)
        self.assertEqual(self.pair.unit_id, self.unit)

    def test_unit_of_archived_way_of_testing_cannot_be_deleted(self):
        self.pair.action_archive()

        with self.assertRaises(UserError):
            self.unit.unlink()

    def test_record_nothing_refers_to_can_be_deleted(self):
        sample_type = self.env[MODEL_SAMPLE_TYPE].create({"name": "Animal feed"})

        sample_type.unlink()

        self.assertFalse(sample_type.exists())

    def test_regulation_is_deleted_with_its_limits(self):
        regulation = self.env[MODEL_REGULATION].create({"code": "QCVN 8-2:2011/BYT", "name": "Bottled water"})
        limit = self.env[MODEL_REGULATION_LIMIT].create(
            {"regulation_id": regulation.id, "parameter_id": self.parameter.id, "limit_text": "Not detected"}
        )

        regulation.unlink()

        self.assertFalse(limit.exists())

    def test_parameter_way_of_testing_and_subcontractor_are_never_deleted(self):
        administrator = self.env.ref("base.user_admin")

        for record in (self.parameter, self.pair, self.subcontractor):
            with self.subTest(model=record._name), self.assertRaises(AccessError):
                record.with_user(administrator).unlink()

    def test_parameter_way_of_testing_and_subcontractor_can_be_archived(self):
        for record in (self.pair, self.subcontractor, self.parameter):
            record.action_archive()

        self.assertFalse(self.pair.active or self.subcontractor.active or self.parameter.active)

    def test_machine_with_service_record_cannot_be_deleted(self):
        self.env[MODEL_MACHINE_SERVICE].create({"machine_id": self.machine.id, "kind": "calibration"})

        with self.assertRaises(UserError):
            self.machine.unlink()

    def test_machine_of_active_way_of_testing_cannot_be_archived_or_deleted(self):
        self.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            {"parameter_method_id": self.pair.id, "machine_id": self.machine.id, "run_minutes": 30}
        )

        for action in (self.machine.action_archive, self.machine.unlink):
            with self.subTest(action=action.__name__), self.assertRaises(UserError):
                action()

    def test_machine_with_only_service_history_can_be_archived(self):
        self.env[MODEL_MACHINE_SERVICE].create({"machine_id": self.machine.id, "kind": "repair"})

        self.machine.action_archive()

        self.assertFalse(self.machine.active)

    def test_chemical_used_by_a_method_cannot_be_deleted(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-901", "name": "Nitric acid"})
        self.method.chemical_ids = chemical

        with self.assertRaises(UserError) as refusal:
            chemical.unlink()

        self.assertIn(self.method.display_name, str(refusal.exception))
