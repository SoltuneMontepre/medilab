"""Actions, scopes and access domains of permissions."""

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_LOCATION

DEPARTMENT_FIELD = "department_id"
TEAM_FIELD = "team_id"
OPERATIONS = {"read": "r", "create": "c", "edit": "u", "archive": "u", "delete": "d"}
SCOPE_DOMAINS = {
    "all": "[(1, '=', 1)]",
    "own_department": f"[('{DEPARTMENT_FIELD}', 'in', user.employee_id.department_id.ids)]",
    "own_team": f"[('{TEAM_FIELD}', 'in', user.employee_id.person_team_id.ids)]",
}
# The field a document type needs for a permission limited to the scope.
SCOPE_FIELDS = {"own_department": DEPARTMENT_FIELD, "own_team": TEAM_FIELD}
# Document type names that are not the model name without medilab.: those of the Odoo models permissions apply to, and
# of MediLab models whose name an Odoo model's document type already has.
DOCUMENT_TYPES = {
    MODEL_LOCATION: "lab_location",
    MODEL_DEPARTMENT: "department",
    "sale.order": "order",
    "stock.location": "location",
    "account.analytic.account": "cost_centre",
    "product.product": "stock_item",
    "product.supplierinfo": "supplier_item",
    "stock.warehouse.orderpoint": "minimum_quantity",
    "purchase.order": "purchase_order",
    "stock.picking": "receipt",
    "stock.lot": "lot",
}
