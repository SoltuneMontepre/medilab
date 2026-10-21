import hashlib
from datetime import timedelta

from odoo import fields
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.laboratory_files import SYNCED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE

# The working files of the bottled water sample: their paths and their first content.
FILES = {
    "calibration": ("HPLC/duong-chuan-Pb.csv", "nong_do_ppb,dien_tich\n0,0\n5,1520\n10,3045"),
    "concentration": ("tinh-toan-nong-do-Pb.csv", "mau,dien_tich,nong_do_ppb\nLAB-26-0415,912,3.0"),
}


def seed_laboratory_file_locks(env):
    """The tester's lock on the calibration curve of the bottled water sample, and on its concentration worksheet a
    lock of the chemistry tester that expired two hours ago and a lock of the tester the administrator released, after
    which the chemistry tester saved the worksheet again. The tester's lock expires like any other, 30 minutes after
    it is seeded."""
    if env.ref("sol_demo.demo_laboratory_file_lock_calibration", raise_if_not_found=False):
        return
    folder = env.ref("sol_demo.demo_laboratory_folder_bottled_water_working")
    tester = env.ref("sol_demo.demo_res_users_tester")
    chemistry_tester = env.ref("sol_demo.demo_res_users_chemistry_tester")
    administrator = env.ref("sol_demo.demo_res_users_administrator")
    hplc_pc = env.ref("sol_demo.demo_laboratory_device_hplc_pc")
    aas_pc = env.ref("sol_demo.demo_laboratory_device_aas_pc")

    def save(file, content, user, device):
        sha256 = hashlib.sha256(content.encode()).hexdigest()
        return file._add_version(
            sha256=sha256,
            size=len(content.encode()),
            storage_key=f"demo/{sha256}",
            source=SYNCED,
            user=user,
            device=device,
            base_version=file.current_version_id,
        )

    files = {}
    versions = {}
    for key, (path, content) in FILES.items():
        files[key] = env[MODEL_LABORATORY_FILE]._get_or_create(folder, path)
        versions[f"{key}_1"] = save(files[key], content, tester, hplc_pc)
    concentration = files["concentration"]

    expired = concentration.with_user(chemistry_tester)._lock(aas_pc)
    taken_at = fields.Datetime.now() - timedelta(hours=2, minutes=30)
    expired.sudo().expires_at = taken_at + expired._duration()
    # Taken two and a half hours ago, as no lock is taken in the past.
    env.cr.execute(SQL("UPDATE medilab_laboratory_file_lock SET create_date = %s WHERE id = %s", taken_at, expired.id))
    expired._expire()
    released = concentration.with_user(tester)._lock(hplc_pc)
    released.with_user(administrator).action_release()
    versions["concentration_2"] = save(
        concentration, "mau,dien_tich,nong_do_ppb\nLAB-26-0415,918,3.02", chemistry_tester, aas_pc
    )
    active = files["calibration"].with_user(tester)._lock(hplc_pc)

    records = {
        **{f"demo_laboratory_file_{key}": file for key, file in files.items()},
        **{f"demo_laboratory_file_version_{key}": version for key, version in versions.items()},
        "demo_laboratory_file_lock_calibration": active,
        "demo_laboratory_file_lock_concentration_expired": expired,
        "demo_laboratory_file_lock_concentration_released": released,
    }
    env["ir.model.data"]._update_xmlids(
        [{"xml_id": f"sol_demo.{xml_id}", "record": record, "noupdate": True} for xml_id, record in records.items()]
    )
