from .schedule_invariants_case import ScheduleInvariantsCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_TESTING_METHOD,
)


class CrossDepartmentCase(ScheduleInvariantsCase):
    """Microbiology also tests lead in-house, by its own method on its own machine, and has its own head."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        method = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "SMEWW 3113B:2017", "name": "Lead by GF-AAS", "field_id": cls.testing_field.id}
        )
        cls.microbiology_way = cls.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": cls.parameter.id,
                "method_id": method.id,
                "unit_id": cls.unit.id,
                "department_id": cls.microbiology.id,
            }
        )
        cls.microbiology_head = cls.create_person(
            "Do Thi Giang",
            cls.microbiology,
            "giang.do",
            permissions=(
                "sample_test.read.all",
                "task.read.own_department",
                "task.edit.own_department",
                "machine_booking.read.own_department",
                "machine_booking.create.own_department",
                "machine_booking.edit.own_department",
            ),
        )
        cls.microbiology_head.tz = "UTC"
        cls.microbiology_machine = cls.env[MODEL_MACHINE].create({"code": "AAS-M1", "name": "Microbiology AAS"})
        cls.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            {
                "parameter_method_id": cls.microbiology_way.id,
                "machine_id": cls.microbiology_machine.id,
                "run_minutes": 40,
            }
        )
