from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_MACHINE_METHOD


@tagged("post_install", "-at_install")
class TestMachineDemo(TransactionCase):
    def test_no_machine_that_runs_the_pesticide_method_can_be_booked(self):
        method = self.env.ref("sol_demo.demo_testing_method_en_15662")
        machines = self.env[MODEL_MACHINE_METHOD].search([("method_id", "=", method.id)]).machine_id
        self.assertEqual(machines, self.env.ref("sol_demo.demo_machine_hplc") | self.env.ref("sol_demo.demo_machine_gc"))
        start = fields.Datetime.now() + timedelta(days=1)
        for machine in machines:
            self.assertTrue(self.env[MODEL_MACHINE_BOOKING]._machine_refusal(machine, start, start + timedelta(hours=1)))
