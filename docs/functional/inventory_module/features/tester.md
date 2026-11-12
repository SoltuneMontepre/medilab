# Features of: Tester

These are the Inventory module's additions to the [Laboratory tester](../../laboratory_module/features/tester.md): a tester opens containers, prepares solutions and records what they use from their team's or department's store.

## I. User stories

- **US-T12** As a tester, I want to open a sealed bottle by scanning its QR code and print its label, so that its opening date, opener and usable date are on the bottle and in the system.
- **US-T13** As a tester, I want to prepare a solution from a recipe by scanning the bottles I use, and print its label, so that the solution, its usable date and what it was made from are on record.
- **US-T14** As a tester, I want to scan the containers I use for a test when I enter its result, so that the result records exactly which containers and lots it used.
- **US-T15** As a tester, I want to record a use outside testing, or waste such as a spill, with its reason, so that stock on hand stays right.
- **US-T16** As a tester, I want to mark a container empty, so that it no longer counts as stock.
- **US-T31** As a tester, I want to scan containers with my phone's camera when I open a bottle, prepare a solution or enter a result, so that I need no scanner at the bench.

## II. Feature details

### 1. Containers and use (US-T12 to US-T16)

Follows [Containers](../overview.md#containers) and [Use](../overview.md#use).

| Rule         | Description                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Store        | The tester's store is every store their team holds. When they have no team, or the team holds none, it is every store their department holds. When neither holds a store, opening, preparing and recording use are refused. |
| Opening      | Only a sealed container that is still usable, in the tester's store, can be opened, and only by someone allowed to edit containers. While the store holds an opened, usable container of the same item with some left, that one is used up or marked empty first; another team's or department's store opens its own. Opening prints its label. The storekeeper records an opening made outside these rules. |
| Preparation  | One preparation is one batch. It deducts the recipe's amounts from the scanned opened bottles, in the order they were scanned, puts the solution into a new opened container in the tester's store and prints its label. An ingredient amount can only be raised above the recipe, and that extra is waste with a reason. The quantity obtained can only be lowered from the yield. |
| Test use     | Scanned containers must be opened, usable and in the store of the person who entered the result. A method that uses an item tracked by container cannot be signed without a scan of that item. A shortage is refused. An outsourced result needs no scan and deducts nothing. |
| After signing | The scanned containers of a result cannot change once it has been signed, and the moves cannot be edited. A retest deducts again. A new version of a result does not. |
| Use by hand  | A use outside a result needs a reason. Waste needs a reason: dropped, spilled, contaminated, wrongly prepared, or Other with what happened written out. A sealed container is wasted whole. |
| Empty        | Marking an opened container empty uses whatever remains and records the reason Marked empty. The container is then depleted. |

Acceptance criteria:

- Opening a sealed bottle sets its status to opened, records who opened it and when, and sets its usable date to the earlier of the opening date plus the item's shelf life after opening and its lot's expiry date.
- Opening one of 5 sealed bottles of a lot leaves the other 4 sealed with their lot's expiry date.
- A container past its usable date, in another store, or opened without permission to edit containers, stays sealed. A lot with no expiry can be opened.
- While the tester's store holds an opened, usable container of the same item with some left, opening another is refused and the message names the opened one; once it is used up or marked empty, the next one opens. An opened container in another team's or department's store, or past its usable date, does not hold back an opening.
- An item without a shelf life after opening keeps its lot's expiry once opened. A shelf life after opening of 0 days makes a container usable on the day it is opened only.
- The storekeeper of a container's store, or of a store above it, records an opening a tester could not make, with who opened it, when and a note. A container then past its usable date is disposed of as expired waste; any other stays opened and its label prints. Someone who does not manage the store, an opening in the future and an opening without a note are refused.
- A sealed, expired or depleted container cannot be used for a test or a preparation.
- A prepared solution's usable date is the earlier of its preparation date plus the recipe's shelf life and the usable dates of the containers it was made from. Its lot is numbered from PC.0001 and its container from that lot, such as PC.0001-01.
- An ingredient amount below the recipe, a quantity obtained above the yield, an extra amount without a waste reason, or a waste reason of Other with nothing written, is refused.
- The first signature of an in-house result deducts the method's usual use from the scanned containers, in scan order, and from the earliest usable lot in the store of the person who entered the result, and links those moves to the result. A later signature does not deduct again, nor does a signature given again after a withdrawal.
- A missing scan, a container of an item the method does not use, or a shortage, is refused and nothing is deducted. The message says how much is still needed, or how much the store holds.
- An outsourced result deducts nothing. A retest deducts again. A new version of a result does not, and it does not keep the scanned containers.
- The scanned containers cannot be changed after the first signature.
- A use needs a reason and goes to the company's Production location. Waste needs a reason and goes to scrap; a reason of Other needs what happened written out, and Expired is not offered. A sealed container is wasted whole and is then disposed of; a partial waste leaves an opened container opened.
- Marking an opened container empty uses what remains, with the reason Marked empty, and the container is depleted; a sealed container is not marked empty. A container whose remaining amount reaches zero is depleted, or disposed of when waste emptied it.

### 2. Mobile (US-T31)

Follows [Medilab Mobile](../../laboratory_module/applications/medilab-mobile.md#scanning-us-hd06-us-t30-us-t31).

| Rule     | Description |
| -------- | ----------- |
| Scanning | The phone's camera reads a container's QR code wherever a container is scanned on the web: opening, preparation and test use. |
| Labels   | The label of an opened bottle or a prepared solution opens as a PDF that the tester prints or shares from the phone. |

Acceptance criteria:

- Opening a sealed bottle by scanning it on the phone sets it opened with its opener and usable date, as on the web.
- Scanning on the phone a container of another store for a test is refused.

## III. Related documents

- [Inventory overview](../overview.md)
- [Laboratory tester](../../laboratory_module/features/tester.md)
- [Team lead](team-lead.md)
