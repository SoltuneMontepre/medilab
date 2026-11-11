import os
import uuid

from .bootstrap import (
    BOOTSTRAP_MODE_VARIABLE,
    BOOTSTRAP_OWNER_VARIABLE,
    set_bootstrap_state,
)

DEMO_PASSWORD_VARIABLE = "MEDILAB_DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "demo"


def post_init_hook(env):
    if os.environ.get(BOOTSTRAP_MODE_VARIABLE) == "1":
        owner = os.environ.get(BOOTSTRAP_OWNER_VARIABLE, "")
        try:
            uuid.UUID(owner)
        except ValueError as error:
            raise ValueError(f"{BOOTSTRAP_OWNER_VARIABLE} must identify this fresh bootstrap attempt") from error
        set_bootstrap_state(env, {"owner": owner, "status": "pending"})
        return

    seed_demo(env)


def seed_demo(env):
    password = os.environ.get(DEMO_PASSWORD_VARIABLE) or DEFAULT_DEMO_PASSWORD
    user_ids = env["ir.model.data"].search([("module", "=", "sol_demo"), ("model", "=", "res.users")]).mapped("res_id")
    for user in env["res.users"].browse(user_ids):
        user.password = password
    from .demo_audit import seed_audit
    from .demo_change_requests import seed_change_requests
    from .demo_cleanup import seed_cleanup
    from .demo_dispatches import seed_agreed_outsourcing, seed_dispatches
    from .demo_finance import seed_finance
    from .demo_laboratory_editing import seed_laboratory_editing
    from .demo_laboratory_file_locks import seed_laboratory_file_locks
    from .demo_laboratory_files import (
        seed_laboratory_file_restores,
        seed_laboratory_file_versions,
        seed_laboratory_files,
        seed_sample_folders,
    )
    from .demo_laboratory_uploads import seed_laboratory_uploads
    from .demo_locks import seed_locks
    from .demo_notifications import seed_notifications
    from .demo_order_templates import seed_order_templates
    from .demo_orders import seed_orders
    from .demo_phones import seed_phones
    from .demo_quotations import seed_quotations, seed_sampling, seed_selected_ways
    from .demo_report_templates import seed_report_templates
    from .demo_reports import seed_reports
    from .demo_results import seed_assessments, seed_results
    from .demo_signing import seed_signing
    from .demo_signing_levels import seed_signing_levels
    from .demo_support import seed_support
    from .demo_tracking import seed_tracking

    if not env.company.chart_template:
        # Order lines take their sales tax and advance invoices their journal from the chart of accounts, which a
        # fresh install loads only once every module is installed.
        env["account.chart.template"].try_loading("vn", env.company)
    seed_orders(env)
    seed_order_templates(env)
    seed_quotations(env)
    seed_selected_ways(env)
    seed_sampling(env)
    seed_results(env)
    seed_assessments(env)
    seed_report_templates(env)
    seed_reports(env)
    seed_change_requests(env)
    seed_signing(env)
    seed_tracking(env)
    seed_dispatches(env)
    seed_agreed_outsourcing(env)
    seed_finance(env)
    seed_audit(env)
    seed_locks(env)
    seed_laboratory_files(env)
    seed_laboratory_file_versions(env)
    seed_laboratory_file_restores(env)
    seed_laboratory_file_locks(env)
    seed_laboratory_uploads(env)
    seed_sample_folders(env)
    seed_laboratory_editing(env)
    seed_phones(env)
    seed_notifications(env)
    seed_cleanup(env)
    seed_support(env)
    seed_signing_levels(env)
