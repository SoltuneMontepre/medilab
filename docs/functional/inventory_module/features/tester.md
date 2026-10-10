# Features of: Tester

These are the Inventory module's additions to the [Laboratory tester](../../laboratory_module/features/tester.md): a tester opens containers, prepares solutions and records what they use from their team's or department's store.

## I. User stories

- **US-T12** As a tester, I want to open a sealed bottle by scanning its QR code and print its label, so that its opening date, opener and usable date are on the bottle and in the system.
- **US-T13** As a tester, I want to prepare a solution from a recipe by scanning the bottles I use, and print its label, so that the solution, its usable date and what it was made from are on record.
- **US-T14** As a tester, I want to scan the containers I use for a test when I enter its result, so that the result records exactly which containers and lots it used.
- **US-T15** As a tester, I want to record a use outside testing, or waste such as a spill, with its reason, so that stock on hand stays right.
- **US-T16** As a tester, I want to mark a container empty, so that it no longer counts as stock.

## II. Feature details

### 1. Containers and use (US-T12 to US-T16)

Follows [Containers](../overview.md#containers) and [Use](../overview.md#use).

| Rule         | Description                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Opening      | Only a sealed, usable container of the tester's store can be opened.                                                         |
| Preparation  | Preparing a solution deducts the recipe's amounts from the scanned opened bottles, creates the solution as an opened container in the tester's store and prints its label. Extra loss is recorded as waste. |
| Test use     | Scanned containers must be opened, usable and in the tester's store. Without a scan, the result cannot be entered for a method that uses an item tracked by container. |
| Waste        | Waste needs a reason: dropped, spilled, contaminated or wrongly prepared.                                                   |

Acceptance criteria:

- Opening a sealed bottle sets its status to opened, records who opened it and when, and sets its usable date to the earlier of the opening date plus the item's shelf life after opening and its lot's expiry date.
- Opening one of 5 sealed bottles of a lot leaves the other 4 sealed with their lot's expiry date.
- A sealed, expired or depleted container cannot be used for a test or a preparation.
- A prepared solution's usable date is the earlier of its preparation date plus the recipe's shelf life and the usable dates of the containers it was made from.
- Entering a result deducts the method's usual use from the scanned containers and links them to the result.
- A container whose remaining amount reaches zero is depleted.

## III. Related documents

- [Inventory overview](../overview.md)
- [Laboratory tester](../../laboratory_module/features/tester.md)
- [Team lead](team-lead.md)
