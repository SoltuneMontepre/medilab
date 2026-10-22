import os

DEMO_PASSWORD_VARIABLE = "MEDILAB_DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "demo"


def post_init_hook(env):
    password = os.environ.get(DEMO_PASSWORD_VARIABLE) or DEFAULT_DEMO_PASSWORD
    user_ids = env["ir.model.data"].search([("module", "=", "sol_demo"), ("model", "=", "res.users")]).mapped("res_id")
    for user in env["res.users"].browse(user_ids):
        user.password = password
    from .demo_audit import seed_audit
    from .demo_change_requests import seed_change_requests
    from .demo_cleanup import seed_cleanup
    from .demo_dispatches import seed_dispatches
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
    from .demo_order_templates import seed_order_templates
    from .demo_orders import seed_orders
    from .demo_quotations import seed_quotations
    from .demo_reports import seed_reports
    from .demo_results import seed_results
    from .demo_signing import seed_signing
    from .demo_subcontracted_report import seed_subcontracted_report
    from .demo_support import seed_support
    from .demo_tracking import seed_tracking

    seed_orders(env)
    seed_order_templates(env)
    seed_quotations(env)
    seed_results(env)
    seed_reports(env)
    seed_change_requests(env)
    seed_signing(env)
    seed_tracking(env)
    # Before the dispatches: its lead test is sent in a dispatch of its own, not in the draft one they leave.
    seed_subcontracted_report(env)
    seed_dispatches(env)
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
    seed_cleanup(env)
    seed_support(env)
