"""Actions, scopes and record rule domains of permissions."""

DEPARTMENT_FIELD = "department_id"
OPERATIONS = {"read": "read", "create": "create", "edit": "write", "archive": "write", "delete": "unlink"}
SCOPE_DOMAINS = {
    "all": "[(1, '=', 1)]",
    "own_department": (
        f"[('{DEPARTMENT_FIELD}.person_ids', 'any', [('user_id', '=', user.id), ('active', '=', True)])]"
    ),
}
