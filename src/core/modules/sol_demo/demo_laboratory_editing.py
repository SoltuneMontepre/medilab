from datetime import timedelta

from odoo import fields
from odoo.fields import Command

from .demo_laboratory_content import content_writer
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION

# The content the two testers saved online in the lead results spreadsheet.
ONLINE_CONTENT = "Pb: 0,004 mg/L, lặp lại 0,005 mg/L, trung bình 0,0045 mg/L"
# How long ago the chemistry tester left the spreadsheet open in the browser without working in it.
IDLE_HOURS = 13


def seed_laboratory_editing(env):
    """The lead results spreadsheet of the bottled water in testing, which the head of chemistry added the tester to:
    edited online by both testers and saved as a third version, after the signed first and the unsigned second, a
    session the chemistry tester left idle until it expired, and the session the tester has open now."""
    if env.ref("sol_demo.demo_laboratory_editing_session_lead_results_open", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    chemistry_tester = env.ref("sol_demo.demo_res_users_chemistry_tester")
    file = env.ref("sol_demo.demo_laboratory_file_bottled_water_lead_results")
    file.folder_id.member_ids = [Command.create({"user_id": tester.id, "role": MEMBER_ROLE})]
    sessions = env[MODEL_LABORATORY_EDITING_SESSION]

    saved = sessions.with_user(tester)._join_or_open(file.with_user(tester))
    sessions.with_user(chemistry_tester)._join_or_open(file.with_user(chemistry_tester))
    version = saved._store_save(
        content=content_writer(env)(ONLINE_CONTENT),
        editor=chemistry_tester,
        editors=tester | chemistry_tester,
    )

    expired = sessions.with_user(chemistry_tester)._join_or_open(file.with_user(chemistry_tester))
    expired.sudo().last_activity_at = fields.Datetime.now() - timedelta(hours=IDLE_HOURS)
    opened = sessions.with_user(tester)._join_or_open(file.with_user(tester))

    env["ir.model.data"]._update_xmlids(
        [
            {
                "xml_id": f"sol_demo.demo_laboratory_editing_session_lead_results_{name}",
                "record": record,
                "noupdate": True,
            }
            for name, record in (("saved", saved), ("expired", expired), ("open", opened))
        ]
        + [
            {
                "xml_id": f"sol_demo.demo_laboratory_file_version_bottled_water_lead_results_{version.number}",
                "record": version,
                "noupdate": True,
            }
        ]
    )
