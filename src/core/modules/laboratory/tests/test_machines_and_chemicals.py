from datetime import date

from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.laboratory.constants.models import MODEL_CHEMICAL, MODEL_MACHINE, MODEL_MACHINE_SERVICE


@tagged("post_install", "-at_install")
class TestMachinesAndChemicals(MasterDataCase):
    def test_method_and_chemical_show_each_other(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "HC-901", "name": "Nitric acid"})

        self.method.chemical_ids = chemical

        self.assertEqual(chemical.method_ids, self.method)

    def test_next_service_dates_follow_the_latest_records(self):
        machine = self.env[MODEL_MACHINE].create({"code": "AAS-09", "name": "AAS 1", "maintenance_interval_days": 30})
        self.env[MODEL_MACHINE_SERVICE].create(
            [
                {
                    "machine_id": machine.id,
                    "kind": "calibration",
                    "service_date": date(2025, 1, 10),
                    "next_due_date": date(2026, 1, 10),
                },
                {
                    "machine_id": machine.id,
                    "kind": "calibration",
                    "service_date": date(2026, 1, 5),
                    "next_due_date": date(2027, 1, 5),
                },
                {"machine_id": machine.id, "kind": "maintenance", "service_date": date(2026, 3, 1)},
            ]
        )

        self.assertEqual(machine.next_calibration_date, date(2027, 1, 5))
        self.assertEqual(machine.next_maintenance_date, date(2026, 3, 31))
