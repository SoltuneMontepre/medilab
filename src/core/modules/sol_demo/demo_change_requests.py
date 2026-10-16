from .demo_results import _test
from odoo.addons.sol_laboratory.constants.models import MODEL_CHANGE_REQUEST, MODEL_TEST_REPORT


def seed_change_requests(env):
    """Change requests through the lab head's chains: one requested on a result, one applied as version 2 of a result,
    one rejected with its reason, and one that replaced an issued report by version 2, issued again."""
    if env.ref("sol_demo.demo_change_request_requested", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    courier = env.ref("sol_demo.demo_res_users_sample_delivery_staff")
    lab_head = env.ref("sol_demo.demo_res_users_lab_head")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    ph = env.ref("sol_demo.demo_test_parameter_ph")
    completed = env.ref("sol_demo.demo_test_request_results").sample_ids.sorted("id")[0]
    by_post = env.ref("sol_demo.demo_test_report_by_post").request_id.sample_ids
    in_person = env.ref("sol_demo.demo_test_report_in_person")

    def raise_on(user, document, change, reason):
        return env[MODEL_CHANGE_REQUEST].with_user(user)._raise(document._name, document.id, change, reason)

    requested = raise_on(
        tester,
        _reported(_test(completed, ph)),
        "Change the pH from 7.2 to 7.4.",
        "The value was copied from the wrong line of the pH meter log.",
    )
    applied = raise_on(
        tester,
        _reported(_test(completed, lead)),
        "Recalculate lead with a dilution factor of 4 instead of 5.",
        "The digest was diluted 4 times; the worksheet shows 5 by mistake.",
    )
    applied.with_user(lab_head).action_sign()
    rejected = raise_on(
        tester,
        _reported(_test(by_post, lead)),
        "Report lead as Not detected.",
        "The value is below the method's limit of quantification.",
    )
    rejected.with_user(lab_head).action_reject(
        "0.004 mg/L is above the method's limit of quantification of 0.002 mg/L, so the measured value stands."
    )
    report = raise_on(
        courier,
        in_person,
        "Reissue the report with the customer's new registered name.",
        "The customer changed its business registration; the report must show the new name.",
    )
    report.with_user(lab_head).action_sign()
    reissued = env[MODEL_TEST_REPORT].browse(report.new_document_id)
    reissued.with_user(lab_head).action_sign()

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True}
            for name, record in (
                ("demo_change_request_requested", requested),
                ("demo_change_request_applied", applied),
                ("demo_change_request_rejected", rejected),
                ("demo_change_request_report", report),
                ("demo_test_report_reissued", reissued),
            )
        ]
    )


def _reported(test):
    return test.result_ids.filtered(lambda result: result.is_reported and not result.is_replaced)
