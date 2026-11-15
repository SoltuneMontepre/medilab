from odoo import api, fields
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_SAMPLE_HANDOVER
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

HANDOVERS = (
    "sol_demo.demo_sample_handover_lead_proposed",
    "sol_demo.demo_sample_handover_lead_marked_urgent",
    "sol_demo.demo_sample_handover_lead_due_soon",
)


def migrate(cr, _version):
    # Chemistry receives the samples of its plan, as a fresh install does, which recalculates the plan.
    env = api.Environment(cr, SUPERUSER_ID, {})
    handovers = env[MODEL_SAMPLE_HANDOVER]
    for xml_id in HANDOVERS:
        handover = reference_as(env[MODEL_SAMPLE_HANDOVER], xml_id, raise_if_not_found=False)
        if handover:
            handovers |= handover
    head = reference_as(env[MODEL_PERSON], "sol_demo.demo_person_head_of_department", raise_if_not_found=False)
    handovers.filtered(lambda handover: not handover.received_at).write(
        {"received_at": fields.Datetime.now(), "received_by_id": head.id if head else False}
    )
