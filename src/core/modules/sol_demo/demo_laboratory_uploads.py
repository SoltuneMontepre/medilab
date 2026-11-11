import hashlib
from datetime import timedelta

from odoo import fields

from .demo_laboratory_content import content_writer
from odoo.addons.sol_laboratory.constants.laboratory_files import LOCKED
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    PREPARED,
    REFUSED,
    SHA256_MISMATCH,
    UNCHANGED,
    UPLOAD_CONFLICT,
    UPLOAD_EXPIRED,
    UPLOAD_FAILED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_MODEL_DATA,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_UPLOAD,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

# The calibration curve the chemistry tester uploaded while the tester held its lock.
REFUSED_CALIBRATION = "nong_do_ppb,dien_tich\n0,0\n5,1518\n10,3041"
# What the AAS computer claimed of a run it changed while uploading it, and the bytes it uploaded.
CLAIMED_RUN = "mau,Pb\nLAB-26-0413,0.009"
UPLOADED_RUN = "mau,Pb\nLAB-26-0413,0.011"
# The chromatogram the HPLC computer is uploading now, and the one it left unfinished last week.
UPLOADING = ("2026/HPLC-run-0420.raw", 48 * 1024 * 1024, hashlib.sha256(b"HPLC-run-0420").hexdigest())
ABANDONED = ("2026/HPLC-run-0398.raw", 20 * 1024 * 1024, hashlib.sha256(b"HPLC-run-0398").hexdigest())


def seed_laboratory_uploads(env):
    """The uploads of the two testers' computers, one in each state a computer reads: the HPLC results' third version
    completed, the AAS conflict, the run file uploaded again unchanged, the calibration curve refused while the tester
    held its lock, a run whose content was not the one claimed, a chromatogram being uploaded now and one left to
    expire."""
    if env.ref("sol_demo.demo_laboratory_upload_hplc_results_3", raise_if_not_found=False):
        return
    tester = env.ref("sol_demo.demo_res_users_tester")
    chemistry_tester = env.ref("sol_demo.demo_res_users_chemistry_tester")
    hplc_pc = env.ref("sol_demo.demo_laboratory_device_hplc_pc")
    aas_pc = env.ref("sol_demo.demo_laboratory_device_aas_pc")
    results = env.ref("sol_demo.demo_laboratory_file_hplc_results")
    run = env.ref("sol_demo.demo_laboratory_file_aas_run")
    calibration = env.ref("sol_demo.demo_laboratory_file_calibration")
    third = env.ref("sol_demo.demo_laboratory_file_version_hplc_results_3")
    conflict = env.ref("sol_demo.demo_laboratory_file_version_hplc_results_4")
    store = content_writer(env)
    now = fields.Datetime.now()

    def of_version(version, user, device):
        return {
            "folder_id": version.file_id.folder_id.id,
            "file_id": version.file_id.id,
            "path": version.file_id.path,
            "claimed_size": version.size,
            "claimed_sha256": version.sha256,
            "user_id": user.id,
            "device_id": device.id,
        }

    def of_new_path(file, path, size, sha256, user, device):
        return {
            "folder_id": file.folder_id.id,
            "path": path,
            "claimed_size": size,
            "claimed_sha256": sha256,
            "user_id": user.id,
            "device_id": device.id,
        }

    failed = store(UPLOADED_RUN, pending=True)
    failed._fail()
    uploading = env[MODEL_LABORATORY_CONTENT].sudo()._new_pending()
    abandoned = env[MODEL_LABORATORY_CONTENT].sudo()._new_pending()
    abandoned._fail()
    refused = store(REFUSED_CALIBRATION)
    path, size, sha256 = UPLOADING
    uploads = {
        "hplc_results_3": {
            **of_version(third, tester, hplc_pc),
            "base_version_id": third.parent_version_id.id,
            "content_id": store("Kết quả HPLC, bản 3", own=True).id,
            "status": COMPLETED,
            "version_id": third.id,
        },
        "hplc_results_aas": {
            **of_version(conflict, chemistry_tester, aas_pc),
            "base_version_id": conflict.file_id.version_ids.filtered(lambda version: version.number == 2).id,
            "content_id": store("Kết quả HPLC, bản AAS", own=True).id,
            "status": UPLOAD_CONFLICT,
            "version_id": conflict.id,
        },
        "aas_run_unchanged": {
            **of_version(run.current_version_id, chemistry_tester, aas_pc),
            "base_version_id": run.current_version_id.id,
            "status": UNCHANGED,
        },
        "calibration_refused": {
            **of_new_path(calibration, calibration.path, refused.size, refused.sha256, chemistry_tester, aas_pc),
            "file_id": calibration.id,
            "base_version_id": calibration.current_version_id.id,
            "content_id": refused.id,
            "status": REFUSED,
            "failure_code": LOCKED,
        },
        "aas_run_failed": {
            **of_new_path(
                run,
                "run-0413.csv",
                len(CLAIMED_RUN.encode()),
                hashlib.sha256(CLAIMED_RUN.encode()).hexdigest(),
                chemistry_tester,
                aas_pc,
            ),
            "content_id": failed.id,
            "status": UPLOAD_FAILED,
            "failure_code": SHA256_MISMATCH,
        },
        "hplc_run_uploading": {
            **of_new_path(results, path, size, sha256, tester, hplc_pc),
            "content_id": uploading.id,
            "multipart_id": laboratory_bucket.create_upload(uploading.object_key) if store.writes else False,
            "status": PREPARED,
        },
        "hplc_run_abandoned": {
            **of_new_path(results, *ABANDONED, tester, hplc_pc),
            "content_id": abandoned.id,
            "status": UPLOAD_EXPIRED,
            "expires_at": now - timedelta(days=6),
        },
    }
    records = {}
    for name, values in uploads.items():
        finalized = values["status"] not in (PREPARED, UPLOAD_EXPIRED)
        records[name] = (
            env[MODEL_LABORATORY_UPLOAD]
            .sudo()
            .create(
                {
                    "idempotency_key": f"demo-{name}",
                    "expires_at": now + timedelta(hours=24),
                    "finalized_at": now if finalized else False,
                    **values,
                }
            )
        )
    env[MODEL_IR_MODEL_DATA]._update_xmlids(
        [
            {"xml_id": f"sol_demo.demo_laboratory_upload_{name}", "record": record, "noupdate": True}
            for name, record in records.items()
        ]
    )
