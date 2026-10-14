from datetime import timedelta

from odoo import fields
from odoo.fields import Command

from .demo_orders import _xml_id
from .demo_results import _enter
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_TASK,
    MODEL_TEST_REQUEST,
)

WATER_SAMPLES = ("Nước giếng khoan hộ gia đình Phú Hòa", "Nước giếng khoan trường tiểu học Phú Hòa")
CABBAGE_SAMPLES = ("Cải bắp chợ Bình Điền lô 1003", "Cải bắp chợ Bình Điền lô 1004")
TRACKING = "Viettel Post, VTP 8402 1157 2210"


def seed_dispatches(env):
    """Outsourced tests in each dispatch status: sent with sample delivery staff and with a delivery service, received
    with results entered by the subcontractor and by a tester, and an accepted suggestion in a draft dispatch."""
    if env.ref("sol_demo.demo_subcontract_dispatch_draft", raise_if_not_found=False):
        return
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    tester = env.ref("sol_demo.demo_res_users_tester")
    subcontractor_user = env.ref("sol_demo.demo_res_users_subcontractor")
    courier = env.ref("sol_demo.demo_person_sample_delivery_staff")
    northern = env.ref("sol_demo.parameter_method_lead_subcontracted")
    southern = env.ref("sol_demo.parameter_method_chlorpyrifos_ug")
    today = fields.Date.today()

    water = _received_tests(env, "nuoc_sach", ("surface_water", "liquid"), "lead", WATER_SAMPLES, "2 bottles")
    cabbage = _received_tests(env, "green_farm", ("cabbage", "solid"), "chlorpyrifos", CABBAGE_SAMPLES, "1 kg")
    carried = _send(head, water[0], northern, today, today + timedelta(days=6), courier_id=courier.id)
    posted = _send(head, cabbage[0], southern, today, today + timedelta(days=9), delivery_service=TRACKING)
    by_subcontractor = _send(head, water[1], northern, today - timedelta(days=8), today, courier_id=courier.id)
    by_tester = _send(head, cabbage[1], southern, today - timedelta(days=10), today, delivery_service=TRACKING)
    (by_subcontractor | by_tester).with_user(head).action_receive()

    env[MODEL_SUBCONTRACT_DISPATCH].with_user(subcontractor_user)._portal_dispatches(
        subcontractor_user, by_subcontractor.id
    )._portal_enter_result(water[1].id, "4.6", "")
    _enter(env, tester, cabbage[1], value=12.4).with_user(tester).action_sign()

    suggested = env.ref("sol_demo.demo_sample_test_lead_outsourcing")
    draft = suggested.with_user(head)._accept_outsourcing(northern)

    for name, dispatch in (
        ("draft", draft),
        ("courier", carried),
        ("delivery_service", posted),
        ("received_subcontractor", by_subcontractor),
        ("received_tester", by_tester),
    ):
        _xml_id(env, f"demo_subcontract_dispatch_{name}", dispatch)


def _received_tests(env, customer, kind, parameter, names, quantity):
    """Received samples whose tests are assigned to the tester and that no machine can finish in time."""
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": env.ref(f"sol_demo.demo_customer_{customer}").id,
            "expected_date": fields.Date.today() + timedelta(days=5),
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": name,
                        "sample_type_id": env.ref(f"sol_demo.sample_type_{kind[0]}").id,
                        "physical_state": kind[1],
                        "test_ids": [Command.create({"parameter_id": env.ref(f"sol_demo.parameter_{parameter}").id})],
                    }
                )
                for name in names
            ],
        }
    )
    request.action_confirm()
    request.sample_ids.with_user(env.ref("sol_demo.demo_res_users_sample_delivery_staff")).action_receive(
        quantity, "good"
    )
    tests = request.sample_ids.test_ids.sorted("id")
    env[MODEL_TASK].search([("document_model", "=", MODEL_SAMPLE_TEST), ("document_id", "in", tests.ids)]).write(
        {
            "assignee_id": env.ref("sol_demo.demo_person_tester").id,
            "assigned_by_id": env.ref("sol_demo.demo_person_head_of_department").id,
            "status": "assigned",
        }
    )
    tests.outsourcing_suggested = True
    return tests


def _send(head, test, way, sent_date, expected_date, **carrier):
    """The head of department accepts the suggestion and sends the test's dispatch."""
    dispatch = test.with_user(head)._accept_outsourcing(way)
    dispatch.write({"sent_date": sent_date, "expected_date": expected_date, **carrier})
    dispatch.action_send()
    return dispatch
