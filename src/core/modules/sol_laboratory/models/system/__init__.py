# The permission mixin is loaded first, because the other models inherit it.
from . import permission_mixin

# isort: split
from . import hr_department, hr_employee, ir_ui_menu, permission, person, role
