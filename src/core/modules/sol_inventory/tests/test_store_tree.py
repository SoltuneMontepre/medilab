from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .stores_case import StoresCase


@tagged("post_install", "-at_install")
class TestStoreTree(StoresCase):
    def test_stores_form_a_tree_under_the_central_store(self):
        self.assertFalse(self.central.parent_store_id)
        self.assertEqual(self.chemistry_store.parent_store_id, self.central)
        self.assertEqual(self.pesticides_store.parent_store_id, self.chemistry_store)
        self.assertEqual(self.fridge.parent_store_id, self.central)

    def test_a_second_store_with_no_store_above_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create_store("Second central store", self.central.location_id)
        with self.assertRaises(ValidationError):
            self.chemistry_store.location_id = self.central.location_id

    def test_a_store_below_the_central_store_is_held_by_a_department_or_team(self):
        with self.assertRaises(ValidationError):
            self.create_store("Microbiology store", self.central)
        with self.assertRaises(ValidationError):
            self.central.holder_id = self.chemistry

    def test_a_team_store_whose_team_does_not_belong_to_the_department_above_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create_store("Pathogens store", self.chemistry_store, self.pathogens)
        with self.assertRaises(ValidationError):
            self.create_store("Pathogens store", self.central, self.pathogens)

    def test_changing_the_store_above_rechecks_the_team_stores_under_it(self):
        with self.assertRaises(ValidationError):
            self.chemistry_store.holder_id = self.microbiology
        with self.assertRaises(ValidationError):
            self.pesticides.parent_id = self.microbiology

    def test_a_store_without_a_manager_cannot_receive_requisitions(self):
        self.central._check_receives_requisitions()

        with self.assertRaises(UserError):
            self.chemistry_store._check_receives_requisitions()

    def test_archiving_a_store_archives_the_locations_inside_it(self):
        self.chemistry_store.action_archive()

        self.assertFalse(self.pesticides_store.active)

    def test_a_team_that_holds_a_store_cannot_be_archived(self):
        with self.assertRaises(UserError):
            self.pesticides.action_archive()

        self.pesticides_store.action_archive()
        self.pesticides.action_archive()
        self.assertFalse(self.pesticides.active)
