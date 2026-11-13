from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tools import SQL

from .demo_results import _enter, _received_request, _test
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING

SAMPLE_NAMES = tuple(f"Nước suối Green Farm 500 mL lô {lot}" for lot in range(1001, 1006))


def seed_figures(env):
    """Lead tests for the testing figures of last month and this month, in UTC. Last month Chemistry approves one test
    on time, cancels one and leaves one overdue; Microbiology approves one late. A Microbiology result rejected last
    month is retested and approved on time this month. Each test tested has a booking."""
    if env.ref("sol_demo.demo_test_request_figures", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_green_farm"),
        [(name, (lead,)) for name in SAMPLE_NAMES],
        expected_date=fields.Date.today() + timedelta(days=7),
    )
    on_time, late, cancelled, overdue, retested = (_test(sample, lead) for sample in request.sample_ids.sorted("id"))

    on_time_result = _approved(env, tester, head, on_time, value=0.004)
    late_result = _approved(env, tester, head, late, value=0.004)
    cancelled.with_user(head).action_cancel("The bottle leaked in transport; too little sample was left.")
    rejected = _enter(env, tester, retested, value=0.2, conclusion="fail")
    rejected.with_user(tester).action_sign()
    rejected.with_user(head).action_reject("The blank read above the LOQ; prepare a new blank and measure again.")
    retested._testing_task().with_user(tester).action_claim()
    retest = _approved(env, tester, head, retested, value=0.005)

    this_month = datetime.combine(fields.Date.today().replace(day=1), time(2))
    last_month = datetime.combine((this_month - timedelta(days=1)).replace(day=1), time(2))
    last_due = last_month + timedelta(days=9, hours=15)
    # The dates below are set in the database; pending writes would overwrite them.
    env.flush_all()
    # (test, received, due date, cancellation)
    for test, received, due, cancelled_at in (
        (on_time, last_month + timedelta(days=2), last_due, None),
        (late, last_month + timedelta(days=3), last_due, None),
        (cancelled, last_month + timedelta(days=3), last_due, last_month + timedelta(days=5)),
        (overdue, last_month + timedelta(days=4), last_due, None),
        (retested, last_month + timedelta(days=20), this_month + timedelta(days=5), None),
    ):
        env.cr.execute(
            SQL(
                "UPDATE medilab_sample SET received_at = %s, create_date = %s WHERE id = %s",
                received,
                received,
                test.sample_id.id,
            )
        )
        env.cr.execute(
            SQL(
                "UPDATE medilab_sample_test SET create_date = %s, due_date = %s, cancelled_at = %s WHERE id = %s",
                received,
                due,
                cancelled_at,
                test.id,
            )
        )
    _backdate_result(env, on_time_result, entered=last_month + timedelta(days=5), signed=last_month + timedelta(days=6))
    _backdate_result(env, late_result, entered=last_month + timedelta(days=5), signed=last_month + timedelta(days=12))
    _backdate_result(env, rejected, entered=last_month + timedelta(days=25), signed=last_month + timedelta(days=26))
    _backdate_result(env, retest, entered=this_month + timedelta(hours=1), signed=this_month + timedelta(hours=3))

    microbiology = env.ref("sol_demo.demo_hr_department_microbiology")
    env.cr.execute(
        SQL(
            "UPDATE medilab_task SET department_id = %s WHERE document_model = 'medilab.sample.test' "
            "AND document_id IN %s",
            microbiology.id,
            (late.id, retested.id),
        )
    )
    env.invalidate_all()

    chemistry_tester = env.ref("sol_demo.demo_person_tester")
    microbiology_tester = env.ref("sol_demo.demo_person_microbiology_tester")
    bookings = env[MODEL_MACHINE_BOOKING].sudo()
    for test, person, start in (
        (on_time, chemistry_tester, last_month + timedelta(days=4)),
        (late, microbiology_tester, last_month + timedelta(days=10)),
        (overdue, chemistry_tester, last_month + timedelta(days=8)),
        (retested, microbiology_tester, this_month),
    ):
        bookings.create(
            {
                "machine_id": env.ref("sol_demo.demo_machine_aas_3").id,
                "sample_test_id": test.id,
                "task_id": test._latest_testing_task().id,
                "person_id": person.id,
                "queued_at": start - timedelta(days=1),
                "starts_at": start,
                "ends_at": start + timedelta(minutes=45),
                "status": "done",
            }
        )

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_test_request_figures", "record": request, "noupdate": True},
            {"xml_id": "sol_demo.demo_sample_test_figures_late", "record": late, "noupdate": True},
            {"xml_id": "sol_demo.demo_sample_test_figures_overdue", "record": overdue, "noupdate": True},
        ]
    )


def _approved(env, tester, head, test, value):
    """A passing result of the tester for the test, sent and approved by the head."""
    result = _enter(env, tester, test, value=value, conclusion="pass")
    result.with_user(tester).action_sign()
    result.with_user(head).action_sign()
    return result


def _backdate_result(env, result, entered, signed):
    env.cr.execute(SQL("UPDATE medilab_test_result SET entered_at = %s WHERE id = %s", entered, result.id))
    env.cr.execute(
        SQL(
            "UPDATE medilab_signature SET create_date = %s "
            "WHERE document_model = 'medilab.test.result' AND document_id = %s",
            signed,
            result.id,
        )
    )
