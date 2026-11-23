from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
    MODEL_PARAMETER_METHOD,
    MODEL_ROLE,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

# Working days defined by the demo parameter-method XML at this version.
TURNAROUNDS = {
    "lead_aas": 5,
    "lead_icpms": 5,
    "lead_subcontracted": 6,
    "coliforms_mpn": 5,
    "coliforms_colony": 4,
    "e_coli_membrane": 4,
    "e_coli_colony": 4,
    "ph_water": 2,
    "ph_soil": 3,
    "chlorpyrifos_quechers": 7,
    "chlorpyrifos_ug": 9,
    "chromium_vi_colorimetry": 3,
    "cadmium_icpms": 5,
    "arsenic_icpms": 5,
}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    methods = env[MODEL_PARAMETER_METHOD]
    for name, days in TURNAROUNDS.items():
        way = reference_as(methods, f"sol_demo.demo_parameter_method_{name}", raise_if_not_found=False)
        if way and not way.turnaround_days:
            way.turnaround_days = days

    # The new role recipients are loaded from XML during the upgrade.
    recipient = reference_as(
        env[MODEL_NOTIFICATION_EVENT_RECIPIENT],
        "sol_demo.demo_notification_event_recipient_department",
        raise_if_not_found=False,
    )
    if (
        recipient
        and recipient.event_id == env.ref("sol_commerce.event_invoice_overdue")
        and recipient.department_id == env.ref("sol_demo.demo_hr_department_chemistry", raise_if_not_found=False)
    ):
        recipient.unlink()

    role = reference_as(env[MODEL_ROLE], "sol_demo.demo_role_sample_delivery_staff", raise_if_not_found=False)
    permission = env.ref("sol_laboratory.permission_sample_edit_all")
    if role and permission in role.permission_ids:
        role.permission_ids = [Command.unlink(persisted_id(permission))]
