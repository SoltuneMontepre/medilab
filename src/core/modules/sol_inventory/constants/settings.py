"""System parameters of the Inventory module and their defaults."""

COSTING_METHOD_PARAMETER = "sol_inventory.costing_method"
COSTING_FIFO = "fifo"
COSTING_MOVING_AVERAGE = "moving_average"
DEFAULT_COSTING_METHOD = COSTING_FIFO
# Odoo's cost method of the stock items' category for each costing method.
ODOO_COST_METHODS = {COSTING_FIFO: "fifo", COSTING_MOVING_AVERAGE: "average"}
EXPIRY_WARNING_PARAMETER = "sol_inventory.expiry_warning_days"
DEFAULT_EXPIRY_WARNING_DAYS = 30
