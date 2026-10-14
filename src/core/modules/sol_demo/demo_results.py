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
)


def seed_results(env):
    """Results through their approval: a completed sample, a failed result awaiting approval beside a cancelled test,
    and a rejected result followed by a text retest."""
    if env.ref("sol_demo.demo_test_request_results", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    ph = env.ref("sol_demo.demo_test_parameter_ph")
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_an_phu"),
        zip(SAMPLE_NAMES, ((lead, ph), (lead, ph), (lead,)), strict=True),
        expected_date=fields.Date.today() + timedelta(days=7),
    )
    completed, waiting, retested = request.sample_ids.sorted("id")

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
    retest = _enter(env, tester, _test(retested, lead), value_text="Not detected", conclusion="pass")
    retest.with_context(lang="vi_VN").value_text = "Không phát hiện"

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_test_request_results", "record": request, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_rejected", "record": rejected, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_retest", "record": retest, "noupdate": True},
        ]
    )


def _received_request(env, customer, samples, **values):
    """A confirmed request of bottled water samples, given as (name, parameters), received in good condition and
    whose testing tasks are assigned to the demo tester."""
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": customer.id,
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": name,
                        "sample_type_id": env.ref("sol_demo.demo_sample_type_bottled_water").id,
                        "physical_state": "liquid",
                        "regulation_id": env.ref("sol_demo.demo_regulation_qcvn_6_1").id,
                        "test_ids": [Command.create({"parameter_id": parameter.id}) for parameter in parameters],
                    }
                )
                for name, parameters in samples
            ],
            **values,
        }
    )
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
    return request


def _test(sample, parameter):
    return sample.test_ids.filtered(lambda test: test.parameter_id == parameter)


def _enter(env, user, test, **values):
    return env[MODEL_TEST_RESULT].with_user(user).create({"sample_test_id": test.id, **values})
