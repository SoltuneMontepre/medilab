from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tools import convert_file

DATA_FILES = (
    "location",
    "testing_method",
    "testing_method_step",
    "test_parameter",
    "parameter_method",
    "machine",
    "machine_service",
    "parameter_method_machine",
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Update mode adds missing room-scheduling records and preserves edited noupdate records.
    for name in DATA_FILES:
        convert_file(env, "sol_demo", f"data/sol_laboratory/{name}.xml", {}, mode="update", noupdate=True)
