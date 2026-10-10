# The permission mixin is loaded first, because the other models inherit it.
from . import permission_mixin

# isort: split
from . import department, permission, person, res_config_settings, role
