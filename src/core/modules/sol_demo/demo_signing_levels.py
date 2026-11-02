from datetime import timedelta

from odoo import fields

from .demo_results import _enter, _received_request, _test
from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE_GRANT

SAMPLE_NAMES = (
    "Nước khoáng An Phú 500 mL lô 1001",
    "Nước khoáng An Phú 500 mL lô 1002",
)


def seed_signing_levels(env):
    """The deputy head of Chemistry, who holds the head of department's role until a date, approves a result the tester
    sent, and sends another result at the tester's level in their own name, which the head of department approves.
    The testers' level then changed so a tester of any department sends results; the sent result keeps the level it
    started with."""
    if env.ref("sol_demo.demo_test_request_signing_levels", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    deputy = env.ref("sol_demo.demo_res_users_backup_signer")
    lead = env.ref("sol_demo.demo_test_parameter_lead")
    grant = env[MODEL_ROLE_GRANT].create(
        {
            "person_id": env.ref("sol_demo.demo_person_backup_signer").id,
            "role_id": env.ref("sol_demo.demo_role_head_of_department").id,
            "date_end": fields.Date.today() + timedelta(days=7),
        }
    )
    request = _received_request(
        env,
        env.ref("sol_demo.demo_customer_an_phu"),
        [(name, (lead,)) for name in SAMPLE_NAMES],
        expected_date=fields.Date.today() + timedelta(days=7),
    )
    approved, sent = request.sample_ids.sorted("id")

    by_backup = _enter(env, tester, _test(approved, lead), value=0.004, conclusion="pass")
    by_backup.with_user(tester).action_sign()
    by_backup.with_user(deputy).action_sign()
    sent_by_deputy = _enter(env, tester, _test(sent, lead), value=0.007, conclusion="pass")
    sent_by_deputy.with_user(deputy).action_sign()
    tester_level = env.ref("sol_demo.demo_approval_level_test_result_signing_tester")
    tester_level.same_department = False
    # The change replaced the level; its external ID follows the chain's new level.
    env["ir.model.data"].search(
        [("module", "=", "sol_demo"), ("name", "=", "demo_approval_level_test_result_signing_tester")]
    ).res_id = tester_level.chain_id.level_ids.filtered(lambda level: level.sequence == tester_level.sequence).id

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": "sol_demo.demo_role_grant_backup_signer_head_of_department", "record": grant, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_request_signing_levels", "record": request, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_approved_by_backup", "record": by_backup, "noupdate": True},
            {"xml_id": "sol_demo.demo_test_result_sent_by_deputy", "record": sent_by_deputy, "noupdate": True},
        ]
    )
