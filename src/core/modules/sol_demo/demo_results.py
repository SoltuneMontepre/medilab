from datetime import timedelta

from odoo import fields
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TEST_REQUEST,
    MODEL_TEST_RESULT,
)

SAMPLE_NAMES = (
    "Nước khoáng An Phú 500 mL lô 0925",
    "Nước uống đóng chai An Phú 1 L lô 0926",
    "Nước tinh khiết An Phú 19 L lô 0927",
    "Nước khoáng An Phú 330 mL lô 0928",
)


def seed_results(env):
    """Results through their approval: a completed sample, a failed result awaiting approval beside a cancelled test,
    a rejected result followed by a text retest under the testing task its rejection opened, and a result the head of
    department entered and sent, awaiting their own approval."""
    if env.ref("sol_demo.demo_test_request_results", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    ph = env.ref("sol_demo.demo_test_parameter_ph")
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_an_phu"),
        zip(SAMPLE_NAMES, ((lead, ph), (lead, ph), (lead,), (lead,)), strict=True),
        expected_date=fields.Date.today() + timedelta(days=7),
    )
    completed, waiting, retested, by_head = request.sample_ids.sorted("id")

    for test, value in ((_test(completed, lead), 0.008), (_test(completed, ph), 7.2)):
        result = _enter(env, tester, test, value=value, conclusion="pass")
        result.with_user(tester).action_sign()
        result.with_user(head).action_sign()
    _enter(env, tester, _test(waiting, lead), value=0.015, conclusion="fail").with_user(tester).action_sign()
    _test(waiting, ph).with_user(head).action_cancel("Too little sample was left for pH after the lead digestion.")
    rejected = _enter(env, tester, _test(retested, lead), value=0.12, conclusion="fail")
    rejected.with_user(tester).action_sign()
    rejected.with_user(head).action_reject(
        "The calibration check standard read 15% high; recalibrate the AAS and measure again."
    )
    _test(retested, lead)._testing_task().with_user(tester).action_claim()
    retest = _enter(env, tester, _test(retested, lead), value_text="Not detected", conclusion="pass")
    retest.with_context(lang="vi_VN").value_text = "Không phát hiện"
    _enter(env, head, _test(by_head, lead), value=0.006, conclusion="pass").with_user(head).action_sign()

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_test_request_results", "record": request, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_rejected", "record": rejected, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_retest", "record": retest, "noupdate": True},
        ]
    )


def seed_assessments(env):
    """Results assessed against a requested regulation: a lead value below the LOD whose suggested text the tester
    confirmed, keeping the measured value, and a lead result on lettuce, on which QCVN 8-2:2011/BYT sets no limit, sent
    as insufficient basis."""
    if env.ref("sol_demo.demo_test_result_below_lod", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    customer = env.ref("sol_demo.demo_customer_green_farm")
    water = _received_request(env, customer, [("Nước suối Green Farm 500 mL lô 1103", (lead,))])
    below_lod = _enter(env, tester, _test(water.sample_ids, lead), value=0.003)
    below_lod.with_user(tester).action_use_value_suggestion()
    below_lod.with_user(tester).conclusion = "pass"
    lettuce = _received_request(
        env,
        customer,
        [("Xà lách Green Farm lô 1104", (lead,))],
        sample_type="sol_demo.demo_sample_type_lettuce",
        physical_state="solid",
        regulation="sol_demo.demo_regulation_qcvn_8_2",
    )
    no_limit = _enter(env, tester, _test(lettuce.sample_ids, lead), value=0.12, conclusion="insufficient")
    no_limit.with_user(tester).action_sign()

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_test_result_below_lod", "record": below_lod, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_insufficient_basis", "record": no_limit, "noupdate": True},
        ]
    )


def _received_request(
    env,
    customer,
    samples,
    sample_type="sol_demo.demo_sample_type_bottled_water",
    physical_state="liquid",
    regulation="sol_demo.demo_regulation_qcvn_6_1",
    **values,
):
    """A confirmed request of samples of the sample type compared with the regulation, given as (name, parameters),
    received in good condition and whose testing tasks are assigned to the demo tester."""
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": customer.id,
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": name,
                        "sample_type_id": env.ref(sample_type).id,
                        "physical_state": physical_state,
                        "regulation_id": env.ref(regulation).id,
                        "test_ids": [Command.create({"parameter_id": parameter.id}) for parameter in parameters],
                    }
                )
                for name, parameters in samples
            ],
            **values,
        }
    )
    _receive(env, request)
    return request


def _receive(env, request):
    """Confirm the request, receive its samples in good condition and assign their testing tasks to the demo tester."""
    request.action_confirm()
    request.sample_ids.with_user(env.ref("sol_demo.demo_res_users_sample_delivery_staff")).action_receive(
        "2 bottles", "good"
    )
    env[MODEL_TASK].search(
        [("document_model", "=", MODEL_SAMPLE_TEST), ("document_id", "in", request.sample_ids.test_ids.ids)]
    ).with_user(env.ref("sol_demo.demo_res_users_head_of_department")).write(
        {
            "assignee_id": env.ref("sol_demo.demo_person_tester").id,
            "assigned_by_id": env.ref("sol_demo.demo_person_head_of_department").id,
            "status": "assigned",
        }
    )


def _test(sample, parameter):
    return sample.test_ids.filtered(lambda test: test.parameter_id == parameter)


def _enter(env, user, test, conclusion: str | None = None, **values):
    """The user's result for the test; the conclusion is set only when the result is in the requested comparison."""
    result = env[MODEL_TEST_RESULT].with_user(user).create({"sample_test_id": test.id, **values})
    if conclusion and result.comparison_requested:
        result.conclusion = conclusion
    return result
