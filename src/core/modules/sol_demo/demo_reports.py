import logging
from datetime import timedelta

from odoo import fields

from .demo_report_templates import prepare_report, report_templates_seeded
from .demo_results import _enter, _received_request, _test
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT

REJECTION = "Lead in sample 1 reads above last month's blank; check the digestion blank and measure again."

_logger = logging.getLogger(__name__)


def seed_reports(env):
    """Test reports of Nước Uống Sạch, whose portal user downloads the issued ones: a draft whose prepared PDF waits
    for the lab head beside a cancelled test and a result the head of department entered and approved, a rejected one
    with a result sent back, issued ones in Vietnamese, English and both, and one whose PDF the digital signing demo
    signs, or fails to sign, at issue. Without the demo templates the reports wait for their PDF."""
    if env.ref("sol_demo.demo_test_report_draft", raise_if_not_found=False):
        return
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    ph = env.ref("sol_demo.demo_test_parameter_ph")
    lab_head = env.ref("sol_demo.demo_res_users_lab_head")
    requests = {
        "draft": _completed_request(
            env,
            (
                ("Nước khoáng Suối Mát 500 mL lô 1001", (lead, ph)),
                ("Nước tinh khiết Suối Mát 19 L lô 1002", (lead, ph)),
            ),
            cancelled=((1, ph),),
            by_head=((1, lead),),
        ),
        "rejected": _completed_request(env, (("Nước uống đóng chai Suối Mát 1 L lô 1003", (lead, ph)),)),
        "by_post": _completed_request(
            env,
            (("Nước khoáng Suối Mát 330 mL lô 1004", (lead, ph)),),
            report_language="vi",
            delivery_method="post",
            delivery_note="Gửi bưu điện đến 12 Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh",
        ),
        "by_email": _completed_request(
            env,
            (("Suoi Mat mineral water 500 mL lot 1005", (lead, ph)),),
            report_language="en",
            delivery_method="email",
            report_recipient_id=env.ref("sol_demo.demo_res_partner_hoa").id,
        ),
        "in_person": _completed_request(env, (("Nước uống đóng chai Suối Mát 5 L lô 1006", (lead, ph)),)),
        "pending": _completed_request(env, (("Nước khoáng Suối Mát 1,5 L lô 1007", (lead, ph)),)),
    }
    reports = {
        name: env[MODEL_TEST_REPORT].search([("request_id", "=", request.id)]) for name, request in requests.items()
    }
    reports["rejected"].with_user(lab_head).action_reject(
        REJECTION, _test(requests["rejected"].sample_ids, lead).result_ids
    )
    if report_templates_seeded(env):
        for name in ("draft", "by_post", "by_email", "in_person", "pending"):
            prepare_report(env, reports[name])
        for name in ("by_email", "in_person"):
            reports[name].with_user(lab_head).action_sign()
        staff = env.ref("sol_demo.demo_res_users_sample_delivery_staff")
        reports["by_email"].with_user(staff).action_record_delivery()
    else:
        _logger.warning("The demo report templates are missing: the demo reports wait for their PDF, unissued.")

    records = {f"demo_test_report_{name}": report for name, report in reports.items()}
    if reports["draft"].candidate_ids:
        records["demo_test_report_candidate_draft"] = reports["draft"].candidate_ids
    env["ir.model.data"]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in records.items()]
    )


def _completed_request(env, samples, cancelled=(), by_head=(), **values):
    """A received request of Nước Uống Sạch whose results are all approved, except the tests cancelled."""
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_nuoc_sach"),
        samples,
        expected_date=fields.Date.today() + timedelta(days=5),
        **values,
    )
    _approve_all(env, request, cancelled, by_head)
    return request


def _approve_all(env, request, cancelled=(), by_head=()):
    """Enter, sign and approve a passing result of every test of the request, and cancel the tests given as
    (sample index, parameter); the head of department enters, sends and approves the tests given in by_head."""
    tester = env.ref("sol_demo.demo_res_users_tester")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    for index, sample in enumerate(request.sample_ids.sorted("id")):
        for test in sample.test_ids:
            if (index, test.parameter_id) in cancelled:
                test.with_user(head).action_cancel("Too little sample was left for pH after the lead digestion.")
                continue
            value = 0.004 if test.parameter_id == env.ref("sol_demo.demo_test_parameter_lead") else 7.2
            entrant = head if (index, test.parameter_id) in by_head else tester
            result = _enter(env, entrant, test, value=value, conclusion="pass")
            result.with_user(entrant).action_sign()
            result.with_user(head).action_sign()
