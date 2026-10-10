import os

DEMO_PASSWORD_VARIABLE = "MEDILAB_DEMO_PASSWORD"


def post_init_hook(env):
    # The login is the password when the variable is unset, as in the test pipeline.
    password = os.environ.get(DEMO_PASSWORD_VARIABLE)
    user_ids = env["ir.model.data"].search([("module", "=", "demo"), ("model", "=", "res.users")]).mapped("res_id")
    for user in env["res.users"].browse(user_ids):
        user.password = password or user.login
