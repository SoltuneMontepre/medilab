from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.laboratory.constants.models import MODEL_JOB_ITEM, MODEL_JOB_RUN, MODEL_SCHEDULED_JOB

SCREENS = {
    "laboratory.menu_scheduled_job": MODEL_SCHEDULED_JOB,
    "laboratory.menu_job_item": MODEL_JOB_ITEM,
    "laboratory.menu_job_run": MODEL_JOB_RUN,
}


@tagged("post_install", "-at_install")
class TestJobScreens(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job = cls.env[MODEL_SCHEDULED_JOB].create({"key": "test.screens", "name": "Screens"})

    def visible_menus(self, user):
        visible = self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        return {xml_id for xml_id in SCREENS if self.env.ref(xml_id).id in visible}

    def test_a_person_without_permissions_sees_no_job_menu(self):
        self.assertEqual(self.visible_menus(self.chemist.user_id), set())

    def test_a_reader_sees_the_job_menus_read_only(self):
        self.grant(self.chemist, "scheduled.job.read.all", "job.item.read.all", "job.run.read.all")

        self.assertEqual(self.visible_menus(self.chemist.user_id), set(SCREENS))
        for model in SCREENS.values():
            views = self.as_person(self.env[model], self.chemist).get_views([(False, "list"), (False, "form")])["views"]
            for view_type, view in views.items():
                root = etree.fromstring(view["arch"])
                with self.subTest(model=model, view=view_type):
                    # The views forbid creating and deleting themselves ("0"); the mixin turns editing off ("False").
                    self.assertTrue(all(root.get(name) in ("0", "False") for name in ("create", "edit", "delete")))

    def test_running_and_rescheduling_need_the_edit_permission(self):
        self.grant(self.chemist, "scheduled.job.read.all")
        job = self.as_person(self.job, self.chemist)

        with self.assertRaises(AccessError):
            job.action_run()
        with self.assertRaises(AccessError):
            job.write({"interval_number": 2})

        self.grant(self.chemist, "scheduled.job.edit.all")
        job.write({"batch_size": 50})
        self.assertEqual(self.job.batch_size, 50)

    def test_retrying_an_item_needs_the_edit_permission(self):
        item = self.env[MODEL_JOB_ITEM].create({"job_id": self.job.id, "item_key": "a", "status": "failed"})
        self.grant(self.chemist, "job.item.read.all")

        with self.assertRaises(AccessError):
            self.as_person(item, self.chemist).action_retry()

        self.grant(self.chemist, "job.item.edit.all")
        self.as_person(item, self.chemist).action_retry()
        self.assertEqual(item.status, "pending")
