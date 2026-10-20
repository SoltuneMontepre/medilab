import hashlib

from odoo.addons.sol_laboratory.constants.laboratory_files import SYNCED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_FILE

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


# The saves of the demo files, in order: the file, who saved it from which computer, its content and the save it was
# made from. The bytes are not in the bucket; the upload flow adds them.
SAVES = (
    ("hplc_results", "2026/HPLC-ket-qua-thang-10.xlsx", "tester", "hplc_pc", "Kết quả HPLC, bản 1", None),
    ("hplc_results", "2026/HPLC-ket-qua-thang-10.xlsx", "chemistry_tester", "aas_pc", "Kết quả HPLC, bản 2", None),
    ("hplc_results", "2026/HPLC-ket-qua-thang-10.xlsx", "tester", "hplc_pc", "Kết quả HPLC, bản 3", None),
    # Saved on the AAS computer from version 2, after the tester had saved version 3: kept as a conflict.
    ("hplc_results", "2026/HPLC-ket-qua-thang-10.xlsx", "chemistry_tester", "aas_pc", "Kết quả HPLC, bản AAS", 2),
    ("aas_run", "run-0412.csv", "chemistry_tester", "aas_pc", "mau,Pb\nLAB-26-0412,0.012", None),
)
FILE_FOLDERS = {"hplc_results": "demo_laboratory_folder_hplc_results", "aas_run": "demo_laboratory_folder_aas_raw_data"}


def seed_laboratory_file_versions(env):
    """A results spreadsheet the two testers saved three times from their computers, with a fourth save kept as a
    conflict, and a run file of the AAS computer."""
    if env.ref("sol_demo.demo_laboratory_file_hplc_results", raise_if_not_found=False):
        return
    files = {}
    xml_ids = []
    for key, path, user_name, computer_name, content, base_number in SAVES:
        if key not in files:
            folder = env.ref(f"sol_demo.{FILE_FOLDERS[key]}")
            files[key] = env[MODEL_LABORATORY_FILE]._get_or_create(folder, path)
            xml_ids.append({"xml_id": f"sol_demo.demo_laboratory_file_{key}", "record": files[key], "noupdate": True})
        file = files[key]
        sha256 = hashlib.sha256(content.encode()).hexdigest()
        version = file._add_version(
            sha256=sha256,
            size=len(content.encode()),
            storage_key=f"demo/{sha256}",
            source=SYNCED,
            user=env.ref(f"sol_demo.demo_res_users_{user_name}"),
            device=env.ref(f"sol_demo.demo_laboratory_device_{computer_name}"),
            base_version=file.version_ids.filtered(lambda version: version.number == base_number),
        )
        xml_ids.append(
            {
                "xml_id": f"sol_demo.demo_laboratory_file_version_{key}_{version.number}",
                "record": version,
                "noupdate": True,
            }
        )
    env["ir.model.data"]._update_xmlids(xml_ids)
