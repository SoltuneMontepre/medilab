# Features of: Team lead

The team lead (tổ trưởng) leads a team of a department and usually manages its store: they request stock from the store above, confirm what arrives and keep the team's stock counted. A team lead also has every feature of a [tester](tester.md). A person who manages a department store, such as a head of department in a laboratory without teams, has the same features for that store.

## I. User stories

- **US-TL01** As a team lead, I want to request stock from the store above mine and see whether it goes over the team's budget, so that the team has what it needs on record.
- **US-TL02** As a team lead, I want to confirm receipt of issued stock by scanning its containers, so that the team's store shows what is really on its shelf.
- **US-TL03** As a team lead, I want to see my team's stock, sealed and opened, with its usable dates and what the team has been charged, so that I can plan use and avoid waste.
- **US-TL04** As a team lead, I want to do a stock take of my team's store, so that its stock on hand matches the shelves.

## II. Feature details

### 1. Team store (US-TL01 to US-TL04)

Follows [Stores](../overview.md#stores), [Movements](../overview.md#movements) and [Budgets](../overview.md#budgets).

| Rule          | Description                                                                                                                 |
| ------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Requesting    | A requisition goes to the store directly above the team's store. A requisition over budget warns the team lead and is escalated. |
| Receiving     | Issued stock enters the team's store when the team lead confirms receipt; containers keep their status and usable date.    |
| Stock         | The team lead sees the stock of the team's store, and the charges of the team's cost centre and how much of its budget is left. |

Acceptance criteria:

- A requisition from a team store can only ask the store directly above it.
- A requisition over budget shows a warning before it is sent.
- Confirming receipt of issued stock adds it to the team's store; a container that was not issued to it is refused.
- A team lead sees the stock and charges of their own team, not those of other teams.

## III. Related documents

- [Inventory overview](../overview.md)
- [Storekeeper](storekeeper.md)
- [Tester](tester.md)
