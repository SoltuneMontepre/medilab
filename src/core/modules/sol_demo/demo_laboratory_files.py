from odoo.fields import Command

from .demo_laboratory_content import content_writer
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, RESTORED, RESULT, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_MODEL_DATA,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

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

    env[MODEL_IR_MODEL_DATA]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in computers.items()]
    )


# The demo files: the folder each one is in and its path.
FILES = {
    "hplc_results": ("demo_laboratory_folder_hplc_results", "2026/HPLC-ket-qua-thang-10.xlsx"),
    "aas_run": ("demo_laboratory_folder_aas_raw_data", "run-0412.csv"),
}
# The saves of the demo files, in order: the file, who saved it from which computer, its content and the number of the
# version it was made from.
SAVES = (
    ("hplc_results", "tester", "hplc_pc", "Kết quả HPLC, bản 1", None),
    ("hplc_results", "chemistry_tester", "aas_pc", "Kết quả HPLC, bản 2", None),
    ("hplc_results", "tester", "hplc_pc", "Kết quả HPLC, bản 3", None),
    # Saved on the AAS computer from version 2, after the tester had saved version 3: kept as a conflict.
    ("hplc_results", "chemistry_tester", "aas_pc", "Kết quả HPLC, bản AAS", 2),
    ("aas_run", "chemistry_tester", "aas_pc", "mau,Pb\nLAB-26-0412,0.012", None),
)


def seed_laboratory_file_versions(env):
    """A results spreadsheet the two testers saved three times from their computers, with a fourth save kept as a
    conflict, and a run file of the AAS computer."""
    if env.ref("sol_demo.demo_laboratory_file_hplc_results", raise_if_not_found=False):
        return
    files = {}
    xml_ids = []
    store = content_writer(env)
    for key, user_name, computer_name, content, base_number in SAVES:
        if key not in files:
            folder_xml_id, path = FILES[key]
            files[key] = env[MODEL_LABORATORY_FILE]._get_or_create(env.ref(f"sol_demo.{folder_xml_id}"), path)
            xml_ids.append({"xml_id": f"sol_demo.demo_laboratory_file_{key}", "record": files[key], "noupdate": True})
        file = files[key]
        version = file._add_version(
            content=store(content),
            source=SYNCED,
            user=reference_as(env[MODEL_RES_USERS], f"sol_demo.demo_res_users_{user_name}"),
            device=reference_as(env[MODEL_LABORATORY_DEVICE], f"sol_demo.demo_laboratory_device_{computer_name}"),
            base_version=file.version_ids.filtered(lambda version, number=base_number: version.number == number),
        )
        xml_ids.append(
            {
                "xml_id": f"sol_demo.demo_laboratory_file_version_{key}_{version.number}",
                "record": version,
                "noupdate": True,
            }
        )
    env[MODEL_IR_MODEL_DATA]._update_xmlids(xml_ids)


# The copy of the AAS run that the chemistry tester saved with the HPLC results: the same bytes as the run file.
RUN_COPY = ("demo_laboratory_folder_hplc_results", "2026/run-0412.csv")


def seed_laboratory_file_restores(env):
    """The tester restoring the first version of the HPLC results from the HPLC computer, its fifth version, and the AAS
    run the chemistry tester copied into the HPLC results folder: each of the two shares the stored content of an older
    version, the restore of the version it restores, the copy of the run file's."""
    if env.ref("sol_demo.demo_laboratory_file_version_hplc_results_5", raise_if_not_found=False):
        return
    results = env.ref("sol_demo.demo_laboratory_file_hplc_results")
    restored = results._add_version(
        source=RESTORED,
        user=env.ref("sol_demo.demo_res_users_tester"),
        device=env.ref("sol_demo.demo_laboratory_device_hplc_pc"),
        restored_from=env.ref("sol_demo.demo_laboratory_file_version_hplc_results_1"),
    )
    folder_xml_id, path = RUN_COPY
    copy = env[MODEL_LABORATORY_FILE]._get_or_create(env.ref(f"sol_demo.{folder_xml_id}"), path)
    run_content = next(content for key, _user, _computer, content, _base in SAVES if key == "aas_run")
    copied = copy._add_version(
        content=content_writer(env)(run_content),
        source=SYNCED,
        user=env.ref("sol_demo.demo_res_users_chemistry_tester"),
        device=env.ref("sol_demo.demo_laboratory_device_aas_pc"),
    )
    env[MODEL_IR_MODEL_DATA]._update_xmlids(
        [
            {"xml_id": xml_id, "record": record, "noupdate": True}
            for xml_id, record in (
                (f"sol_demo.demo_laboratory_file_version_hplc_results_{restored.number}", restored),
                ("sol_demo.demo_laboratory_file_hplc_run_copy", copy),
                ("sol_demo.demo_laboratory_file_version_hplc_run_copy_1", copied),
            )
        ]
    )


# The saves of the lead results of the bottled water in testing, by the chemistry tester: the head of the department
# signs the first, and the second is newer and not signed.
SAMPLE_RESULT_SAVES = ("Pb: 0,004 mg/L", "Pb: 0,004 mg/L, lặp lại 0,005 mg/L")


def seed_sample_folders(env):
    """The raw-data and result folders the head of chemistry created for the bottled water in testing, with the
    chemistry tester as a member, and its lead results spreadsheet: the first version signed by the head, the second
    newer and not signed."""
    if env.ref("sol_demo.demo_laboratory_folder_bottled_water_testing_result", raise_if_not_found=False):
        return
    head = env.ref("sol_demo.demo_res_users_head_of_department")
    tester = env.ref("sol_demo.demo_res_users_chemistry_tester")
    sample = env.ref("sol_demo.demo_sample_bottled_water_testing")
    folders = sample._create_laboratory_folders(head)
    for folder in folders:
        folder.member_ids = [Command.create({"user_id": tester.id, "role": MEMBER_ROLE})]
    results = folders.filtered(lambda folder: folder.category == RESULT)
    file = env[MODEL_LABORATORY_FILE]._get_or_create(results, "Pb-ket-qua.xlsx")
    device = env.ref("sol_demo.demo_laboratory_device_aas_pc")
    store = content_writer(env)
    versions = []
    for content in SAMPLE_RESULT_SAVES:
        versions.append(file._add_version(content=store(content), source=SYNCED, user=tester, device=device))
        if len(versions) == 1:
            versions[0].with_user(head).action_sign()

    xml_ids = [
        {"xml_id": f"sol_demo.demo_laboratory_folder_bottled_water_testing_{folder.category}", "record": folder}
        for folder in folders
    ]
    xml_ids.append({"xml_id": "sol_demo.demo_laboratory_file_bottled_water_lead_results", "record": file})
    xml_ids += [
        {
            "xml_id": f"sol_demo.demo_laboratory_file_version_bottled_water_lead_results_{version.number}",
            "record": version,
        }
        for version in versions
    ]
    env[MODEL_IR_MODEL_DATA]._update_xmlids([{**xml_id, "noupdate": True} for xml_id in xml_ids])
