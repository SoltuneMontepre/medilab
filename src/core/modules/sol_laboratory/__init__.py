from . import controllers, models


def uninstall_hook(env):
    # Drop the accreditation upgrade snapshot left for verification after 20.0.1.6.0.
    cr = env.cr
    cr.execute("DROP TABLE IF EXISTS medilab_is_accredited_upgrade_snapshot")
    cr.execute("DROP TABLE IF EXISTS medilab_is_accredited_upgrade_snapshot_done")
