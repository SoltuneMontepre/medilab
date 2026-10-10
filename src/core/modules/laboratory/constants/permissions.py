"""Actions, scopes and record rule domains of permissions."""

DEPARTMENT_FIELD = "department_id"
# The Odoo operation each action is enforced with; sign has none, its group alone marks who may sign.
OPERATIONS = {"read": "read", "create": "create", "edit": "write", "archive": "write", "delete": "unlink"}
# The record rule domain of each scope, evaluated with the user.
SCOPE_DOMAINS = {
    "all": "[(1, '=', 1)]",
    "own_department": (
        f"[('{DEPARTMENT_FIELD}.person_ids', 'any', [('user_id', '=', user.id), ('active', '=', True)])]"
    ),
}
