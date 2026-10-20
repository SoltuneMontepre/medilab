from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE

COMPUTERS = (
    (
        "demo_laboratory_device_hplc_pc",
        "demo_res_users_tester",
        "7d1c3f0e-2a4b-4c55-9e1d-0b6f2a9c4e11",
        "PC-HPLC-01",
        "windows",
    ),
    (
        "demo_laboratory_device_aas_pc",
        "demo_res_users_chemistry_tester",
        "c2b8e6a4-5f3d-4e7a-8b19-6d0e4a2f7c35",
        "PC-AAS-01",
        "linux",
    ),
    (
        "demo_laboratory_device_lost_laptop",
        "demo_res_users_chemistry_tester",
        "9f4a1d7c-3e2b-4a68-b5c0-8e7d6f1a2b93",
        "LAPTOP-HUNG",
        "windows",
    ),
)


def seed_laboratory_files(env):
    """Both testers signed in on a computer each, the chemistry tester's lost laptop revoked, the old GC folder turned
    off and the 2025 report drafts archived with their retention date."""
    if env.ref("sol_demo.demo_laboratory_device_hplc_pc", raise_if_not_found=False):
        return
    administrator = env.ref("sol_demo.demo_res_users_administrator")
    computers = {}
    for xml_id, user_xml_id, client_uid, name, platform in COMPUTERS:
        user = env.ref(f"sol_demo.{user_xml_id}")
        devices = env[MODEL_LABORATORY_DEVICE].with_user(user)
        # As signing in from Medilab Sync makes it; nobody needs the key, which only its hash keeps.
        _key, key_id = devices._new_key(name)
        computers[xml_id] = devices.sudo().create(
            {"user_id": user.id, "client_uid": client_uid, "name": name, "platform": platform, "api_key_id": key_id}
        )
    computers["demo_laboratory_device_lost_laptop"].with_user(administrator).action_revoke()
    env.ref("sol_demo.demo_laboratory_folder_gc_old").with_user(administrator).action_turn_off()
    env.ref("sol_demo.demo_laboratory_folder_report_drafts_2025").with_user(administrator).action_archive_folder()

    env["ir.model.data"]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in computers.items()]
    )
