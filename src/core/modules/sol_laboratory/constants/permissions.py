"""Actions, scopes and access domains of permissions."""

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT

DEPARTMENT_FIELD = "department_id"
OPERATIONS = {"read": "r", "create": "c", "edit": "u", "archive": "u", "delete": "d"}
SCOPE_DOMAINS = {
    "all": "[(1, '=', 1)]",
    "own_department": f"[('{DEPARTMENT_FIELD}', 'in', user.employee_id.department_id.ids)]",
}
# Document type names of the Odoo models permissions apply to, which carry no medilab. prefix.
ODOO_DOCUMENT_TYPES = {MODEL_DEPARTMENT: "department"}
