import os

DEMO_PASSWORD_VARIABLE = "MEDILAB_DEMO_PASSWORD"


def post_init_hook(env):
    # Demo users sign in with the password of the local development configuration, or with their login when it is
    # not set, such as in the test pipeline.
    password = os.environ.get(DEMO_PASSWORD_VARIABLE)
    user_ids = env["ir.model.data"].search([("module", "=", "demo"), ("model", "=", "res.users")]).mapped("res_id")
    for user in env["res.users"].browse(user_ids):
        user.password = password or user.login
