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
    from .demo_dispatches import seed_dispatches
    from .demo_orders import seed_orders
    from .demo_quotations import seed_quotations
    from .demo_reports import seed_reports
    from .demo_results import seed_results
    from .demo_tracking import seed_tracking

    seed_orders(env)
    seed_quotations(env)
    seed_results(env)
    seed_reports(env)
    seed_change_requests(env)
    seed_tracking(env)
    seed_dispatches(env)
    seed_audit(env)
