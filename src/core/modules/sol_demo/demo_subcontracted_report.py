from datetime import timedelta

from odoo import fields

from .demo_orders import _xml_id
from .demo_results import _enter, _received_request, _test
from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACT_DISPATCH, MODEL_TEST_REPORT

SAMPLE = "Nước khoáng Suối Mát 1,5 L lô 1007"


def seed_subcontracted_report(env):
    """A draft test report of Nước Uống Sạch whose lead result Northern tested and entered on the portal, beside a pH
    result tested in-house."""
    if env.ref("sol_demo.demo_test_report_subcontracted", raise_if_not_found=False):
        return
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    tester = env.ref("sol_demo.demo_res_users_tester")
    subcontractor_user = env.ref("sol_demo.demo_res_users_subcontractor")
    today = fields.Date.today()
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_nuoc_sach"),
        ((SAMPLE, (lead, env.ref("sol_demo.demo_test_parameter_ph"))),),
        expected_date=today + timedelta(days=5),
    )
    outsourced = _test(request.sample_ids, lead)
    outsourced.outsourcing_suggested = True
    dispatch = outsourced.with_user(head)._accept_outsourcing(
        env.ref("sol_demo.demo_parameter_method_lead_subcontracted")
    )
    dispatch.write(
        {
            "sent_date": today - timedelta(days=6),
            "expected_date": today,
            "courier_id": env.ref("sol_demo.demo_person_sample_delivery_staff").id,
        }
    )
    dispatch.action_send()
    dispatch.action_receive()
    by_subcontractor = (
        env[MODEL_SUBCONTRACT_DISPATCH]
        .with_user(subcontractor_user)
        ._portal_dispatches(subcontractor_user, dispatch.id)
        ._portal_enter_result(outsourced.id, "3.2", "")
    )
    by_subcontractor.with_user(tester).conclusion = "pass"
    in_house = _enter(env, tester, request.sample_ids.test_ids - outsourced, value=7.4, conclusion="pass")
    for result in by_subcontractor | in_house:
        result.with_user(tester).action_sign()
        result.with_user(head).action_sign()

    _xml_id(env, "demo_test_report_subcontracted", env[MODEL_TEST_REPORT].search([("request_id", "=", request.id)]))
