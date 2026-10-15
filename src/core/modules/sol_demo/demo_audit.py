from odoo.addons.sol_laboratory.constants.models import MODEL_CHEMICAL

RAISED_LEAD_PRICE = 280000


def seed_audit(env):
    """Loading the demo writes the create entries; the administrator adds an edit, an archive and a deletion."""
    price = env.ref("sol_demo.demo_parameter_price_lead")
    if price.list_price == RAISED_LEAD_PRICE:
        return
    administrator = env.ref("sol_demo.demo_res_users_administrator")
    price.with_user(administrator).list_price = RAISED_LEAD_PRICE
    env.ref("sol_demo.demo_test_parameter_cadmium").with_user(administrator).action_archive()
    duplicate = (
        env[MODEL_CHEMICAL]
        .with_user(administrator)
        .create({"code": "HC-001-2", "name": "Nitric acid 65%", "cas_number": "7697-37-2"})
    )
    duplicate.unlink()
