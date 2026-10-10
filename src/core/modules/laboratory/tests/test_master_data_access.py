from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import MasterDataCase
from odoo.addons.laboratory.constants.models import (
    MODEL_CHEMICAL,
    MODEL_MACHINE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_QUALITY_REGISTRATION,
    MODEL_REGULATION,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
)

MASTER_DATA_MODELS = [
    MODEL_CHEMICAL,
    MODEL_MACHINE,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_QUALITY_REGISTRATION,
    MODEL_REGULATION,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
]


@tagged("post_install", "-at_install")
class TestMasterDataAccess(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = new_test_user(cls.env, login="tester", groups="base.group_user")

    def test_non_administrator_reads_but_cannot_change(self):
        parameter = self.parameter.with_user(self.tester)

        self.assertEqual(parameter.method_ids.unit_id.name, "mg/g")
        for action in (
            lambda: parameter.create({"name": "Cadmium (Cd)", "main_group_id": self.group.id}),
            lambda: parameter.write({"name": "Lead"}),
            parameter.action_archive,
            parameter.unlink,
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()

    def test_non_administrator_sees_no_actions(self):
        for model in MASTER_DATA_MODELS:
            records = self.env[model].with_user(self.tester)
            views = records.get_views([(False, "list"), (False, "form")])["views"]
            for view_type, view in views.items():
                root = etree.fromstring(view["arch"])
                with self.subTest(model=model, view=view_type):
                    self.assertEqual(
                        [root.get("create"), root.get("edit"), root.get("delete")], ["False", "False", "False"]
                    )
            with self.subTest(model=model, action="archive"):
                self.assertTrue(records.fields_get(["active"], ["readonly"])["active"]["readonly"])

    def test_administrator_keeps_every_action(self):
        views = self.env[MODEL_TEST_PARAMETER].get_views([(False, "form")])["views"]

        self.assertIsNone(etree.fromstring(views["form"]["arch"]).get("create"))
        self.assertFalse(self.env[MODEL_TEST_PARAMETER].fields_get(["active"], ["readonly"])["active"]["readonly"])
