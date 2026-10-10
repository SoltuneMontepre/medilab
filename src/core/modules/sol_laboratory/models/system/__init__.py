# The permission mixin is loaded first, because the other models inherit it.
from . import permission_mixin

# isort: split
from . import department, ir_actions_act_window_view, ir_ui_view, permission, person, role
