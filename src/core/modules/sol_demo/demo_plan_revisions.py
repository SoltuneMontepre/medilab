from datetime import datetime, timedelta

from odoo import fields
from odoo.fields import Command

from .demo_orders import _xml_id
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_METHOD,
    MODEL_OVERTIME,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_SAMPLE_TYPE,
    MODEL_PERSON,
    MODEL_SAMPLE_HANDOVER,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.type_values import value_as

# A gas chromatograph run takes one 4-hour interval, as in the scheduling spec's GC-01 example.
RUN = timedelta(hours=4)
URGENT_REASON = "Khách hàng cần kết quả để thông quan lô hàng."
DUE_REASON = "Khách hàng đã xác nhận ngày cần kết quả với bộ phận kinh doanh."
OVERTIME_REASON = "Kết quả khẩn không được làm chậm các mẫu đã nhận trước."
# (machine number, parameter, method code and name, tester, samples of Z, Y and X, OverTime recorded)
SCENARIOS = (
    (
        2,
        "Diazinon",
        "LAB-GC-02",
        "Foods of plant origin — Determination of diazinon residues by gas chromatography",
        "Vo Thi Mai",
        ("Cải bắp chợ Bình Điền lô 2101", "Cải bắp chợ Bình Điền lô 2102", "Cải bắp chợ Bình Điền lô 2103"),
        False,
    ),
    (
        3,
        "Malathion",
        "LAB-GC-03",
        "Foods of plant origin — Determination of malathion residues by gas chromatography",
        "Bui Van Nam",
        ("Cải bắp chợ Bình Điền lô 2201", "Cải bắp chợ Bình Điền lô 2202", "Cải bắp chợ Bình Điền lô 2203"),
        True,
    ),
)


def seed_plan_revisions(env):
    """The GC-01 example of the scheduling spec on two gas chromatographs, each run by a tester of its own. Z and Y are
    normal tests booked in the first two 4-hour intervals, all three tests have the same internal due date, and urgent X
    needs Z's interval. On GC-02 the plan revision holds back the moves of Z and Y, which would pass their due dates,
    until Sales records the customers' agreement; on GC-03 the head recorded OverTime, so the revision puts X, Z and Y
    before the due date and waits for the head's approval."""
    for scenario in SCENARIOS:
        if not env.ref(f"sol_demo.demo_machine_gc_{scenario[0]}", raise_if_not_found=False):
            _seed_scenario(env, *scenario)


def _seed_scenario(env, number, parameter_name, method_code, method_name, tester_name, samples, overtime):
    chemistry = env.ref("sol_demo.demo_hr_department_chemistry")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    today = fields.Date.today()
    machine = env[MODEL_MACHINE].create(
        {
            "code": f"GC-0{number}",
            "name": f"Gas chromatograph {number}",
            "model": "GC-2030",
            "manufacturer": "Shimadzu",
            "location_id": env.ref("sol_demo.demo_location_chemistry_bench_3").id,
            "service_ids": [
                Command.create(
                    {
                        "kind": "calibration",
                        "service_date": today - timedelta(days=60),
                        "next_due_date": today + timedelta(days=300),
                        "performed_by": "Quality Assurance and Testing Centre",
                        "reference": f"HC-2026-10{number}",
                    }
                )
            ],
        }
    )
    method = env[MODEL_TESTING_METHOD].create(
        {"code": method_code, "name": method_name, "field_id": env.ref("sol_demo.demo_testing_field_chemistry").id}
    )
    group = env.ref("sol_demo.demo_parameter_group_organophosphates")
    parameter = env[MODEL_TEST_PARAMETER].create(
        {"name": parameter_name, "group_ids": [Command.set([group.id])], "main_group_id": group.id}
    )
    way = env[MODEL_PARAMETER_METHOD].create(
        {"parameter_id": parameter.id, "method_id": method.id, "department_id": chemistry.id}
    )
    cabbage = env.ref("sol_demo.demo_sample_type_cabbage")
    env[MODEL_PARAMETER_METHOD_SAMPLE_TYPE].create(
        {
            "parameter_id": parameter.id,
            "parameter_method_id": way.id,
            "sample_type_id": cabbage.id,
            "unit_id": env.ref("sol_demo.demo_measurement_unit_mg_kg").id,
            "lod": 0.003,
            "loq": 0.01,
            "result_decimals": 3,
            "is_default": True,
        }
    )
    env[MODEL_MACHINE_METHOD].create({"machine_id": machine.id, "method_id": method.id, "duration_minutes": 240})
    tester = env[MODEL_PERSON].create(
        {
            "name": tester_name,
            "tz": env.company.tz,
            "department_id": chemistry.id,
            "team_id": env.ref("sol_demo.demo_hr_department_pesticide_residues").id,
            "role_ids": [Command.set([env.ref("sol_demo.demo_role_tester").id])],
        }
    )
    env[MODEL_PARAMETER_AUTHORIZATION].create({"person_id": tester.id, "parameter_id": parameter.id})

    names_z, names_y, names_x = samples
    z_test = _received_test(env, parameter, names_z, tester, today + timedelta(days=10))
    y_test = _received_test(env, parameter, names_y, tester, today + timedelta(days=10))
    for test in (z_test, y_test):
        test.with_user(head).action_approve_booking()
    y = y_test.booking_ids.filtered(lambda booking: booking.status == "scheduled")
    # Every test of the example is due when Y's interval ends; with OverTime, when the OverTime ends.
    due_date = value_as(y.ends_at, datetime) + (RUN if overtime else timedelta())
    x_test = _received_test(env, parameter, names_x, tester, today + timedelta(days=10))
    for test in (z_test, y_test, x_test):
        test.write({"due_date": due_date, "due_date_reason": DUE_REASON})
    if overtime:
        env[MODEL_OVERTIME].with_user(head).create(
            {"person_id": tester.id, "starts_at": y.ends_at, "ends_at": y.ends_at + RUN, "reason": OVERTIME_REASON}
        )
    x_test.with_user(head)._mark_urgent(URGENT_REASON)

    key = f"gc_{number}"
    _xml_id(env, f"demo_machine_{key}", machine)
    _xml_id(env, f"demo_test_parameter_{key}", parameter)
    _xml_id(env, f"demo_person_{key}_tester", tester)
    for name, test in (("z", z_test), ("y", y_test), ("urgent", x_test)):
        _xml_id(env, f"demo_sample_test_{key}_{name}", test)


def _received_test(env, parameter, sample_name, tester, expected_date):
    """A confirmed request of one cabbage sample tested for the parameter, received in good condition and by the
    chemistry head, with its testing task assigned to the tester."""
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": env.ref("sol_demo.demo_customer_green_farm").id,
            "committed_date": expected_date,
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": sample_name,
                        "sample_type_id": env.ref("sol_demo.demo_sample_type_cabbage").id,
                        "physical_state": "solid",
                        "test_ids": [Command.create({"parameter_id": parameter.id})],
                    }
                )
            ],
        }
    )
    request.action_confirm()
    request.sample_ids.with_user(env.ref("sol_demo.demo_res_users_sample_delivery_staff")).action_receive(
        "1 kg", "good"
    )
    env[MODEL_SAMPLE_HANDOVER].with_user(head).receive_by_label(request.sample_ids.code)
    test = request.sample_ids.test_ids
    env[MODEL_TASK].search([("document_model", "=", test._name), ("document_id", "=", test.id)]).write(
        {
            "assignee_id": tester.id,
            "assigned_by_id": env.ref("sol_demo.demo_person_head_of_department").id,
            "status": "assigned",
        }
    )
    return test
