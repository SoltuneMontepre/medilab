from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import MasterDataCase
from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import (
    MASTER_DATA_MODELS,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
)


@tagged("post_install", "-at_install")
class TestMasterDataAccess(MasterDataCase, PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = new_test_user(cls.env, login="tester", groups="base.group_user")

    def user_with(self, model, *actions):
        code = model.removeprefix("medilab.").replace(".", "_")
        groups = ["base.group_user"] + [f"sol_laboratory.group_permission_{code}_{action}_all" for action in actions]
        return new_test_user(self.env, login=f"{code}.{'.'.join(actions)}", groups=",".join(groups))

    def unused_records(self):
        # One record nothing refers to for each type that can be archived, so archiving it is never refused.
        return [
            self.env[MODEL_UNIT_CATEGORY].create({"name": "Volume"}),
            self.env[MODEL_MEASUREMENT_UNIT].create({"name": "pg/g", "category_id": self.category.id}),
            self.env[MODEL_TESTING_FIELD].create({"code": "TST", "name": "Sensory testing"}),
            self.env[MODEL_TESTING_METHOD].create(
                {"code": "TCVN 9999:2026", "name": "Taste panel", "field_id": self.testing_field.id}
            ),
            self.env[MODEL_PARAMETER_GROUP].create({"name": "Pesticides"}),
            self.create_parameter("Cadmium (Cd)", self.group),
            self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"}),
        ]

    def archive_offered(self, records):
        return not records.fields_get(["active"], ["readonly"])["active"]["readonly"]

    def form_flag(self, records, name):
        return etree.fromstring(records.get_views([(False, "form")])["views"]["form"]["arch"]).get(name)

    def test_master_data_access_comes_from_permissions(self):
        # Besides reading, which every internal user does, every access is a permission's.
        everyone_reads = self.env.ref("base.group_user")
        permission_groups = self.env[MODEL_PERMISSION].search([]).group_id
        accesses = self.env["ir.access"].search([("model_id.model", "in", MASTER_DATA_MODELS)])
        others = accesses.filtered(
            lambda access: (
                access.group_id not in permission_groups
                and (access.group_id != everyone_reads or access.operation != "r")
            )
        )

        self.assertFalse(others.mapped("name"))
        for model in MASTER_DATA_MODELS:
            with self.subTest(model=model):
                self.assertIn(model, self.env.registry[MODEL_PERMISSION_MIXIN]._inherit_children)

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
            if "active" in records._fields:
                with self.subTest(model=model, action="archive"):
                    self.assertFalse(self.archive_offered(records))

    def test_archive_permission_archives_without_editing(self):
        for record in self.unused_records():
            with self.subTest(model=record._name):
                archiver = record.with_user(self.user_with(record._name, "archive"))

                self.assertTrue(self.archive_offered(archiver))
                self.assertEqual(self.form_flag(archiver, "edit"), "False")
                with self.assertRaises(AccessError):
                    archiver.write({"name": "Renamed"})
                archiver.action_archive()
                self.assertFalse(record.active)

    def test_edit_permission_edits_without_archiving(self):
        for record in self.unused_records():
            with self.subTest(model=record._name):
                editor = record.with_user(self.user_with(record._name, "edit"))

                self.assertFalse(self.archive_offered(editor))
                self.assertIsNone(self.form_flag(editor, "edit"))
                with self.assertRaises(AccessError):
                    editor.action_archive()
                editor.write({"name": "Renamed"})
                self.assertEqual(record.name, "Renamed")

    def test_subcontractor_permissions_cover_its_company_contact(self):
        user = self.user_with(MODEL_SUBCONTRACTOR, "create", "edit")
        subcontractors = self.env[MODEL_SUBCONTRACTOR].with_user(user)

        subcontractor = subcontractors.create({"name": "Northern Testing Laboratory", "city": "Hanoi"})
        subcontractor.write({"name": "Northern Testing Centre", "phone": "024 3826 1234"})

        self.assertEqual(
            [subcontractor.name, subcontractor.city, subcontractor.phone],
            ["Northern Testing Centre", "Hanoi", "024 3826 1234"],
        )
        with self.assertRaises(AccessError):
            subcontractor.write({"partner_id": self.env.ref("base.partner_admin").id})
        with self.assertRaises(AccessError):
            subcontractors.create({"name": "Southern Laboratory", "partner_id": self.env.ref("base.partner_admin").id})

    def test_own_department_permission_edits_only_their_departments_ways_of_testing(self):
        self.pair.department_id = self.chemistry
        cadmium = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.create_parameter("Cadmium (Cd)", self.group).id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "department_id": self.microbiology.id,
            }
        )
        self.grant(self.chemist, "parameter_method.edit.own_department")

        self.as_person(self.pair, self.chemist).write({"lod": 0.01})
        self.assertEqual(self.pair.lod, 0.01)
        with self.assertRaises(AccessError):
            self.as_person(cadmium, self.chemist).write({"lod": 0.01})

    def test_administrator_keeps_every_action(self):
        administrator = self.env.ref("base.user_admin")
        categories = self.env[MODEL_UNIT_CATEGORY].with_user(administrator)
        root = etree.fromstring(categories.get_views([(False, "form")])["views"]["form"]["arch"])

        self.assertEqual([root.get("create"), root.get("edit"), root.get("delete")], [None, None, None])
        self.assertTrue(self.archive_offered(categories))
        category = categories.create({"name": "Volume"})
        category.write({"name": "Volume in liquid"})
        category.action_archive()
        self.assertFalse(category.active)
        category.unlink()
        self.assertFalse(category.exists())
        self.pair.with_user(administrator).action_archive()
        self.parameter.with_user(administrator).action_archive()
        self.assertFalse(self.parameter.active)
