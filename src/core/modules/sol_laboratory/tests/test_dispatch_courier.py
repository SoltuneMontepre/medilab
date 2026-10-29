from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.settings import SAMPLE_DELIVERY_ROLE_PARAMETER


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestDispatchCourier(DispatchCase):
    def test_only_people_holding_the_sample_delivery_staff_role_carry_a_dispatch(self):
        # The head reads people to choose who takes the dispatch.
        self.grant(self.head, "person.read.all")
        dispatch = self.as_person(self.outsource(), self.head)

        self.assertEqual(dispatch.courier_choice_ids, self.courier)
        with self.assertRaises(ValidationError):
            dispatch.courier_id = self.tester
        dispatch.courier_id = self.courier

        self.assertEqual(dispatch.courier_id, self.courier)

    def test_nobody_carries_a_dispatch_until_the_role_is_named_in_the_settings(self):
        self.env["ir.config_parameter"].sudo().set_int(SAMPLE_DELIVERY_ROLE_PARAMETER, None)
        dispatch = self.as_person(self.outsource(), self.head)

        self.assertFalse(dispatch.courier_choice_ids)
        with self.assertRaises(ValidationError):
            dispatch.courier_id = self.courier
