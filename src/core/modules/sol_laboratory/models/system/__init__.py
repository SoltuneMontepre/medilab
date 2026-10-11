# The mixins are loaded first, because the other models inherit them.
from . import archive_mixin, audit_mixin, permission_mixin

# isort: split
from . import (
    audit_change,
    audit_entry,
    audit_report,
    department,
    ir_config_parameter,
    permission,
    person,
    res_users,
    role,
)
