"""External ids of records the Inventory module refers to from Python code."""

COST_CENTRE_PLAN = "sol_inventory.analytic_plan_cost_centres"
# The views of the Stores screen.
STORE_VIEWS = ("sol_inventory.view_medilab_store_list", "sol_inventory.view_medilab_store_form")
# QR labels of containers, on 2 by 1 inch and 1.5 by 1 inch labels.
CONTAINER_LABEL_REPORT = "sol_inventory.action_report_container_label"
SMALL_CONTAINER_LABEL_REPORT = "sol_inventory.action_report_container_label_small"
# The Containers screen.
CONTAINER_ACTION = "sol_inventory.action_medilab_container"
# Why stock was wasted: dropped, spilled, contaminated, wrongly prepared, or another reason written out.
SCRAP_DROPPED = "sol_inventory.scrap_reason_dropped"
SCRAP_SPILLED = "sol_inventory.scrap_reason_spilled"
SCRAP_CONTAMINATED = "sol_inventory.scrap_reason_contaminated"
SCRAP_WRONGLY_PREPARED = "sol_inventory.scrap_reason_wrongly_prepared"
SCRAP_OTHER = "sol_inventory.scrap_reason_other"
# Why expired stock was disposed of.
SCRAP_EXPIRED = "sol_inventory.scrap_reason_expired"
# The product category of every stock item, whose costing method follows the costing method setting.
STOCK_ITEM_CATEGORY = "sol_inventory.product_category_stock_item"
# The Stock on Hand screen, the stock expiring soon and the expired stock waiting for disposal.
STOCK_ON_HAND_ACTION = "sol_inventory.action_medilab_stock_on_hand"
EXPIRING_ACTION = "sol_inventory.action_medilab_expiring"
DISPOSAL_ACTION = "sol_inventory.action_medilab_disposal"
# Who sees the value of stock: Odoo's stock managers and the holders of the stock read permission.
VALUE_GROUPS = "stock.group_stock_manager,sol_laboratory.group_permission_stock_read_all"
# Odoo's stock managers, who keep Odoo's own Inventory reports.
STOCK_MANAGER_GROUP = "stock.group_stock_manager"
# Odoo's Reporting menu of its Inventory app, and the MediLab screens under it.
STOCK_REPORTING_MENU = "stock.menu_warehouse_report"
STOCK_SCREEN_MENUS = ("sol_inventory.menu_stock_on_hand", "sol_inventory.menu_expiring")
