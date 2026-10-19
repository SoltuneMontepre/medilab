from datetime import timedelta

from odoo import fields

from odoo.addons.sol_laboratory.constants.models import MODEL_DOCUMENT_LOCK


def seed_locks(env):
    """A draft test request the sample delivery staff is editing while sales waits to be told it is free, a lock
    released on save, one that expired after the inactivity period and one the administrator released."""
    if env.ref("sol_demo.demo_document_lock_active", raise_if_not_found=False):
        return
    courier = env.ref("sol_demo.demo_res_users_sample_delivery_staff")
    tester = env.ref("sol_demo.demo_res_users_tester")
    sales = env.ref("sol_demo.demo_res_users_sales")
    administrator = env.ref("sol_demo.demo_res_users_administrator")
    locks = env[MODEL_DOCUMENT_LOCK]

    def take(user, document):
        return locks.with_user(user)._take(document.with_user(user))

    draft = env.ref("sol_demo.demo_test_request_draft")
    active = take(courier, draft)
    locks.with_user(sales)._watch(draft)
    saved = take(courier, env.ref("sol_demo.demo_test_request_confirmed"))
    saved._release("saved")
    expired = take(tester, env.ref("sol_demo.demo_regulation_qcvn_6_1"))
    expired.last_activity_at = fields.Datetime.now() - timedelta(hours=2)
    expired._release("expired")
    stuck = take(tester, env.ref("sol_demo.demo_test_request_testing"))
    stuck.with_user(administrator).action_release()

    env["ir.model.data"]._update_xmlids(
        [
            {"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True}
            for name, record in (
                ("demo_document_lock_active", active),
                ("demo_document_lock_saved", saved),
                ("demo_document_lock_expired", expired),
                ("demo_document_lock_stuck", stuck),
            )
        ]
    )
