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
