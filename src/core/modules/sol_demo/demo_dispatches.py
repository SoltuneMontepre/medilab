import io
from datetime import timedelta

from odoo import fields
from odoo.fields import Command
from odoo.tools.binary import BinaryBytes
from odoo.tools.pdf import PdfFileWriter

from .demo_orders import _xml_id
from .demo_results import _enter
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.settings import SAMPLE_DELIVERY_ROLE_PARAMETER
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

WATER_SAMPLES = ("Nước giếng khoan hộ gia đình Phú Hòa", "Nước giếng khoan trường tiểu học Phú Hòa")
CABBAGE_SAMPLES = ("Cải bắp chợ Bình Điền lô 1003", "Cải bắp chợ Bình Điền lô 1004")
RIVER_SAMPLES = ("Nước sông Sài Gòn trạm bơm Hòa Phú", "Nước kênh Thầy Cai cống Tân Hiệp")
EMERGENCY_REASON = "Máy AAS đang sửa, khách hàng cần kết quả chì trước hạn kiểm tra của cơ quan y tế."
TRACKING = "Viettel Post, VTP 8402 1157 2210"
AGREED_SAMPLE = ("Nước giếng khoan xã Tân Thạnh Đông",)
IN_HOUSE_SAMPLE = ("Nước giếng khoan xã Phước Vĩnh An",)
REPORT_NAME = "PKQ-NTL-2026-0412.pdf"
SURFACE_WATER = ("surface_water", "liquid")


def seed_dispatches(env):
    """Outsourced tests in each dispatch status: sent with sample delivery staff and with a delivery service, received
    with results entered by the subcontractor and by a tester, and an accepted suggestion and a test outsourced straight
    away in a draft dispatch. A river water test with no suggestion is left for outsourcing straight away. The sample
    delivery staff role is the one that carries dispatches."""
    delivery_role = env.ref("sol_demo.demo_role_sample_delivery_staff")
    env["ir.config_parameter"].sudo().set_int(SAMPLE_DELIVERY_ROLE_PARAMETER, delivery_role.id)
    if env.ref("sol_demo.demo_subcontract_dispatch_draft", raise_if_not_found=False):
        return
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    tester = env.ref("sol_demo.demo_res_users_tester")
    subcontractor_user = env.ref("sol_demo.demo_res_users_subcontractor")
    courier = env.ref("sol_demo.demo_person_sample_delivery_staff")
    northern = env.ref("sol_demo.demo_parameter_method_lead_subcontracted")
    southern = env.ref("sol_demo.demo_parameter_method_chlorpyrifos_ug")
    today = fields.Date.today()

    water = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", WATER_SAMPLES, "2 bottles")
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
    river = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", RIVER_SAMPLES, "2 bottles")
    river.outsourcing_suggested = False
    river[0].with_user(head)._outsource_now(northern, EMERGENCY_REASON)
    _xml_id(env, "demo_sample_test_lead_emergency_outsourced", river[0])
    _xml_id(env, "demo_sample_test_lead_emergency", river[1])

    for name, dispatch in (
        ("draft", draft),
        ("courier", carried),
        ("delivery_service", posted),
        ("received_subcontractor", by_subcontractor),
        ("received_tester", by_tester),
    ):
        _xml_id(env, f"demo_subcontract_dispatch_{name}", dispatch)


def seed_agreed_outsourcing(env):
    """A lead test the customer accepted on the subcontracted way, in Northern's draft dispatch through it, and one
    accepted in-house, which is not outsourced straight away until a revised quotation; the dispatch received with the
    subcontractor's result keeps its report."""
    if env.ref("sol_demo.demo_sample_test_lead_agreed_subcontracted", raise_if_not_found=False):
        return
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    northern = env.ref("sol_demo.demo_parameter_method_lead_subcontracted")
    in_house = env.ref("sol_demo.demo_parameter_method_lead_aas")

    agreed = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", AGREED_SAMPLE, "2 bottles", way=northern)
    agreed.with_user(head)._accept_outsourcing(northern)
    changed = _received_tests(env, "nuoc_sach", SURFACE_WATER, "lead", IN_HOUSE_SAMPLE, "2 bottles", way=in_house)
    changed.outsourcing_suggested = False
    # A blank page stands for the report Northern Testing Laboratory returned.
    report = PdfFileWriter()
    report.add_blank_page(width=595, height=842)
    stream = io.BytesIO()
    report.write(stream)
    received = env.ref("sol_demo.demo_subcontract_dispatch_received_subcontractor")
    received.with_user(head).write({"report_file": BinaryBytes(stream.getvalue()), "report_filename": REPORT_NAME})

    _xml_id(env, "demo_sample_test_lead_agreed_subcontracted", agreed)
    _xml_id(env, "demo_sample_test_lead_agreed_in_house", changed)


def _received_tests(env, customer, kind, parameter, names, quantity, way=None):
    """Received samples whose tests are assigned to the tester and that no machine can finish in time, on the way of
    testing the customer accepted when one is given."""
    accepted = {"parameter_method_id": way.id, "accepted_method_id": way.id} if way else {}
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": env.ref(f"sol_demo.demo_customer_{customer}").id,
            "expected_date": fields.Date.today() + timedelta(days=5),
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": name,
                        "sample_type_id": reference_as(
                            env[MODEL_SAMPLE_TYPE], f"sol_demo.demo_sample_type_{kind[0]}"
                        ).id,
                        "physical_state": kind[1],
                        "test_ids": [
                            Command.create(
                                {
                                    "parameter_id": reference_as(
                                        env[MODEL_TEST_PARAMETER], f"sol_demo.demo_test_parameter_{parameter}"
                                    ).id,
                                    **accepted,
                                }
                            )
                        ],
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
