# Features of: Administrator

These are the Inventory module's additions to the [Laboratory administrator](../../laboratory_module/features/admin.md), who also maintains the departments, their teams and team leads.

Inventory keeps its stores, cost centres, recipes and budgets in its own tables and does not add columns to Laboratory tables. The tables are drawn in [inventory.prisma](../../../infrastructure/database/inventory/inventory.prisma).

## I. User stories

### Stores and cost centres

- **US-AD21** As an administrator, I want to set up the stores as a tree, with the department or team that holds each one and the person who manages it, so that the stores match the laboratory's size.
- **US-AD22** As an administrator, I want to give each department and team its cost centre code, so that charges match the codes in the accounting software.

### Recipes

- **US-AD23** As an administrator, I want to maintain recipes with the chemicals and amounts one preparation uses and the shelf life of the solution, so that every preparation is made, deducted and labelled the same way.

### Budgets and settings

- **US-AD24** As an administrator, I want to set the supply budget of each cost centre for a quarter or a year and choose the role that approves over-budget requisitions, so that spending is watched without stopping urgent testing.
- **US-AD25** As an administrator, I want to set the costing method and the charge point, and issue keys for the accounting API, so that charges follow the laboratory's accounting policy.

## II. Feature details

### 1. Stores and cost centres (US-AD21 to US-AD22)

Follows [Stores](../overview.md#stores) and [Costs](../overview.md#costs).

| Rule         | Description                                                                                                         |
| ------------ | ------------------------------------------------------------------------------------------------------------------- |
| Central store | Exactly one store has no store above it: the central store.                                                       |
| Holder       | A department store is held by a department, a team store by a team of the department whose store is above it.       |
| Manager      | Each store names the person who manages it. The manager of the central store holds the storekeeper role.            |
| Cost centre  | Each department and each team that holds a store has a cost centre code, unique across the laboratory.              |

Acceptance criteria:

- A second store with no store above it is refused.
- A team store whose team does not belong to the department above it is refused.
- A store without a manager cannot receive requisitions.
- Two cost centres with the same code are refused.

### 2. Recipes (US-AD23)

Follows [Containers](../overview.md#containers).

| Rule        | Description                                                                                         |
| ----------- | --------------------------------------------------------------------------------------------------- |
| Content     | A recipe names the solution it makes, the quantity one preparation gives, each chemical item with its amount, and the shelf life in days. |
| Ingredients | A recipe's ingredients are items tracked by container, or other recipes' solutions.                 |

Acceptance criteria:

- A recipe without a shelf life or without an ingredient cannot be saved.
- A recipe cannot use its own solution as an ingredient.

### 3. Budgets and settings (US-AD24 to US-AD25)

Follows [Budgets](../overview.md#budgets) and [Accounting export](../overview.md#accounting-export).

| Rule      | Description                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------------- |
| Period    | A budget covers one cost centre for one quarter or one year; budgets of one cost centre do not overlap.            |
| Settings  | The costing method, the charge point and the over-budget role are [system parameters](../../shared.md#sh-03-configuration-through-settings-and-system-parameters). |
| API keys  | Each accounting API key has a name and can be revoked; a revoked key is refused.                                   |

Acceptance criteria:

- Two budgets of one cost centre for overlapping periods are refused.
- Changing the costing method or the charge point applies to charges made after the change; earlier charges keep their values.
- A request to the accounting API with a revoked or unknown key is refused.

## III. Related documents

- [Inventory overview](../overview.md)
- [Laboratory administrator](../../laboratory_module/features/admin.md)
- [Storekeeper](storekeeper.md)
