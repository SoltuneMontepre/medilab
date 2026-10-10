# Stock costing and charges

Stories: US-SK10, US-SK12, US-SK13, US-SK14, US-TL01, US-TL03, US-AD24, US-AD25

## Goal

Every move of stock carries a cost, stock on hand has a value, and stock is charged once to the cost centre that holds it. This spec states how a move is costed under each costing method, which moves charge or credit a cost centre under each charge point, how budgets are used up and how the charges reach the accounting software.

## Design

### Settings

| System parameter             | Values                   | Default             |
| ---------------------------- | ------------------------ | ------------------- |
| `inventory.costing_method`   | `fifo`, `moving_average` | `fifo`              |
| `inventory.charge_point`     | `on_issue`, `on_use`     | `on_issue`          |
| `inventory.over_budget_role` | a role                   | none: no escalation |

A change applies to moves done after it; moves and charges already made keep their unit cost and value.

### Cost of a move

Every move stores `unit_cost` when it is done, and the value of a move is its quantity times its unit cost. A receipt takes the unit price of its receipt line, excluding VAT, and writes it on the lot it creates. Every other move takes its unit cost from the costing method in force:

| Stock                | First in, first out                                                                                                                                    | Moving average          |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| Tracked by container | The container's lot unit cost; for a prepared solution, the container's own unit cost                                                                  | The item's average cost |
| Tracked by lot       | The lot's unit cost                                                                                                                                    | The item's average cost |
| Tracked by quantity  | The receipts of the item still holding stock, oldest first: the move takes from each one's `remaining_quantity` and costs at their weighted unit price | The item's average cost |

- **Average cost.** Every receipt updates the item's `average_cost` to the value of the stock on hand plus the value received, divided by the quantity on hand plus the quantity received. Moves other than receipts do not change it. When the method changes to moving average, the average cost of each item is set from its stock value under first in, first out.
- **Remaining quantity.** A receipt of an item tracked by quantity starts with its received quantity as `remaining_quantity`. Moves that take stock out of the laboratory (consumption, waste, disposal, a missing quantity) lower the oldest receipts' remaining quantity first; moves between locations and stores do not. A quantity found at a stock take is added to the newest receipt.
- **Prepared solution.** A preparation's unit cost is the value of the moves that deducted its ingredients and waste, divided by the quantity made, written on the solution's container.

### Stock value

Stock on hand is valued per item, lot, container and location by the costing method in force: under first in, first out, each container at its unit cost or its lot's, each lot quant at its lot's unit cost, and an item tracked by quantity at the value of its receipts' remaining quantities; under moving average, every quantity at its item's average cost. Stock in transit counts in no store.

### Cost centre of a store

A store held by a department or team is charged to that department's or team's cost centre. The central store has no holder and no cost centre: its stock is the laboratory's, and nothing in it is charged. A store whose holder has no cost centre cannot receive requisitions or transfers.

### Charges

A move charges or credits a cost centre with a `StockCharge` of its quantity, unit cost and value, negative for a credit, posted on the day the move is done. Stock is charged once, at the charge point:

| Move                                   | On issue                                                       | On use                    |
| -------------------------------------- | -------------------------------------------------------------- | ------------------------- |
| Requisition received into a store      | Issue, charged to the receiving cost centre                    | None                      |
| Transfer received                      | Transfer: credit the sending, charge the receiving cost centre | None                      |
| Consumption for a test result          | None                                                           | Consumption, billable     |
| Consumption by hand                    | None                                                           | Consumption, not billable |
| Waste                                  | None                                                           | Waste                     |
| Disposal                               | None                                                           | Disposal                  |
| Stock take: missing                    | None                                                           | Adjustment                |
| Stock take: found                      | Adjustment, charged                                            | None                      |
| Preparation, relocation inside a store | None                                                           | None                      |

A move in the central store charges nothing under either charge point. A charge never changes after it is made; a correction is a new move with its own charge.

### Cost per test

The cost of a sample test is the value of the consumption moves of its result, whatever the charge point, so the material cost of each way of testing can be reported from the moves.

### Budgets

A budget covers one cost centre from `date_from` to `date_to`, a quarter or a year; the budgets of one cost centre never overlap. The budget used is the sum of the values of the cost centre's charges posted in the period, credits included.

A requisition estimates its value from each line's requested quantity at the unit cost the costing method would give now. When the budget used plus that estimate exceeds the budget of the period, the requester sees a warning before sending it; once sent, the requisition is marked `over_budget` and escalated: it waits for a person holding the over-budget role to approve it before the store manager can approve it. Without an over-budget role set, an over-budget requisition is only warned. A cost centre without a budget for the period is never over budget.

### Accounting export

The storekeeper exports the charges posted in a period as CSV or Excel, one row per charge:

| Column       | Value                                                       |
| ------------ | ----------------------------------------------------------- |
| Posting date | `posting_date`                                              |
| Cost centre  | The cost centre's code                                      |
| Item         | The item's code                                             |
| Charge type  | issue, consumption, waste, disposal, adjustment or transfer |
| Billable     | yes or no                                                   |
| Quantity     | Signed quantity in the item's unit                          |
| Unit         | The item's unit                                             |
| Unit cost    | `unit_cost`                                                 |
| Value        | `value`                                                     |

The same rows are served by a REST endpoint, `GET /api/medilab/inventory/charges?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&offset=0&limit=500`, as JSON with the total count. The request carries `Authorization: Bearer <key>`. The administrator issues a key with a name; the key is generated once, shown once and stored only as its SHA-256 hash. A revoked or unknown key gets 401. Every request is recorded in the audit trail with the key's name, never the key.

### Document types of this feature

| Document type      | Actions                    | Scopes                        |
| ------------------ | -------------------------- | ----------------------------- |
| Stock charge       | read                       | all, own_department, own_team |
| Budget             | read, create, edit, delete | all                           |
| Accounting API key | read, create, edit         | all                           |

Charges are created by moves only; nobody creates, edits or deletes one by hand. An API key is revoked by editing it, never deleted.

## Related documents

- [Inventory overview](../functional/inventory_module/overview.md)
- [Inventory administrator](../functional/inventory_module/features/admin.md)
- [Storekeeper](../functional/inventory_module/features/storekeeper.md)
- [Team lead](../functional/inventory_module/features/team-lead.md)
- [Permissions](permissions.md)
- [Database diagram](../infrastructure/database/inventory/inventory.prisma)
