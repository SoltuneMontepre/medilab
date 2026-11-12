from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

# The demo phones signed in on Medilab Mobile, by the end of their xml id.
PHONES = (
    "tester_phone",
    "tester_old_phone",
    "head_of_department_phone",
    "sample_delivery_staff_phone",
    "sales_phone",
    "sales_tablet",
)


def seed_phones(env):
    """The phones of the tester, the head of department, the sample delivery staff and the sales signed in, and the
    tester's old iPhone revoked."""
    phones = {
        name: reference_as(env[MODEL_LABORATORY_DEVICE], f"sol_demo.demo_laboratory_device_{name}") for name in PHONES
    }
    if any(phone.api_key_id or phone.revoked_at for phone in phones.values()):
        return
    for phone in phones.values():
        # As signing in from Medilab Mobile makes it; nobody needs the key, which only its hash keeps.
        _key, key_id = phone.with_user(phone.user_id)._new_key(phone.name, phone=True)
        phone.sudo().api_key_id = key_id
    phones["tester_old_phone"].with_user(env.ref("sol_demo.demo_res_users_administrator")).action_revoke()
