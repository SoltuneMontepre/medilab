from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_demo.demo_phones import seed_phones
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_MOBILE_DEVICE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

# The demo push tokens: the phone each belongs to and whether it is on.
TOKENS = {
    "demo_mobile_device_active": ("sales_phone", True),
    "demo_mobile_device_off": ("tester_old_phone", False),
    "demo_mobile_device_failed": ("sales_tablet", True),
    "demo_mobile_device_sample_delivery_staff": ("sample_delivery_staff_phone", True),
}


def migrate(cr, _version):
    # The Laboratory upgrade gave each demo push token a signed-out phone of its own; the demo data now names the
    # demo phones, which are signed in here.
    env = api.Environment(cr, SUPERUSER_ID, {})
    placeholders = env[MODEL_LABORATORY_DEVICE]
    for xml_id, (phone, active) in TOKENS.items():
        token = reference_as(env[MODEL_MOBILE_DEVICE], f"sol_demo.{xml_id}", raise_if_not_found=False)
        if not token:
            continue
        token = token.with_context(active_test=False)
        placeholders |= token.laboratory_device_id
        token.write(
            {
                "laboratory_device_id": env.ref(f"sol_demo.demo_laboratory_device_{phone}").id,
                "active": active,
            }
        )
    placeholders = placeholders.filtered(lambda device: device.client_uid.startswith("push-token-"))
    if placeholders:
        # The tokens' new phones reach the database before their placeholders are deleted, which would cascade to them.
        env.flush_all()
        cr.execute("DELETE FROM medilab_laboratory_device WHERE id IN %s", [tuple(placeholders.ids)])
    seed_phones(env)
