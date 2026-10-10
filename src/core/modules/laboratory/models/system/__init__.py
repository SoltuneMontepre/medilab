# The permission mixin is loaded first, because the other models inherit it.
from . import permission_mixin

# isort: split
from . import department, job_item, job_run, permission, person, res_config_settings, role, scheduled_job
