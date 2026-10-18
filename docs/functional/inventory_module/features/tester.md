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
| Store        | The tester's store is every store their team holds. When they have no team, or the team holds none, it is every store their department holds. When neither holds a store, opening, preparing and recording use are refused. |
| Opening      | Only a sealed container that is still usable, in the tester's store, can be opened, and only by someone allowed to edit containers. Opening prints its label. |
| Preparation  | One preparation is one batch. It deducts the recipe's amounts from the scanned opened bottles, in the order they were scanned, puts the solution into a new opened container in the tester's store and prints its label. An ingredient amount can only be raised above the recipe, and that extra is waste with a reason. The quantity obtained can only be lowered from the yield. |
| Test use     | Scanned containers must be opened, usable and in the store of the person who entered the result. A method that uses an item tracked by container cannot be signed without a scan of that item. A shortage is refused. An outsourced result needs no scan and deducts nothing. |
| After signing | The scanned containers of a result cannot change once it has been signed, and the moves cannot be edited. A retest deducts again. A new version of a result does not. |
| Use by hand  | A use outside a result needs a reason. Waste needs a reason: dropped, spilled, contaminated or wrongly prepared. A sealed container is wasted whole. |
| Empty        | Marking a container empty uses whatever remains and records the reason Marked empty. The container is then depleted. |

Acceptance criteria:

- Opening a sealed bottle sets its status to opened, records who opened it and when, and sets its usable date to the earlier of the opening date plus the item's shelf life after opening and its lot's expiry date.
- Opening one of 5 sealed bottles of a lot leaves the other 4 sealed with their lot's expiry date.
- A container past its usable date, in another store, or opened without permission to edit containers, stays sealed. A shelf life after opening of 0 makes the usable date the opening day. A lot with no expiry can be opened.
- A sealed, expired or depleted container cannot be used for a test or a preparation.
- A prepared solution's usable date is the earlier of its preparation date plus the recipe's shelf life and the usable dates of the containers it was made from. Its lot is numbered from PC.0001 and its container from that lot, such as PC.0001-01.
- An ingredient amount below the recipe, a quantity obtained above the yield, or an extra amount without a waste reason, is refused.
- The first signature of an in-house result deducts the method's usual use from the scanned containers, in scan order, and from the earliest usable lot in the store of the person who entered the result, and links those moves to the result. A later signature does not deduct again.
- A missing scan, a container of an item the method does not use, or a shortage, is refused and nothing is deducted. The message says how much is still needed, or how much the store holds.
- An outsourced result deducts nothing. A retest deducts again. A new version of a result does not, and it does not keep the scanned containers.
- The scanned containers cannot be changed after the first signature.
- A use needs a reason and goes to the company's Production location. Waste needs a reason and goes to scrap. A sealed container is wasted whole and is then disposed of; a partial waste leaves an opened container opened.
- Marking a container empty uses what remains, with the reason Marked empty, and the container is depleted. A container whose remaining amount reaches zero is depleted, or disposed of when waste emptied it.

## III. Related documents

- [Inventory overview](../overview.md)
- [Laboratory tester](../../laboratory_module/features/tester.md)
- [Team lead](team-lead.md)
