# Inventory Module Overview

The Inventory module keeps the laboratory's stock: chemicals and reagents, consumables and machine spare parts. It tracks lots and their expiry, where stock is kept and how it moves, what each test uses, and buys stock from suppliers. It depends on the Laboratory module, which holds the chemicals themselves (name, CAS number, storage conditions) and the testing methods. The tables are drawn in [inventory.prisma](../../infrastructure/database/inventory/inventory.prisma).

## Stock

| Rule          | Description                                                                                                                                   |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Items         | A stock item is a chemical or reagent, a consumable or a spare part, counted in one unit. A chemical item stocks one Laboratory chemical.        |
| Locations     | Stock is kept in a tree of locations, such as a warehouse, a room and a fridge. A location can belong to a department and states its storage conditions. |
| Lots          | Chemicals are kept by lot, with the expiry date printed on the container and the manufacturer's certificate. Consumables and spare parts can be kept without lots. |
| Stock on hand | The quantity of each item, lot and location is kept up to date by moves.                                                                      |
| Moves         | Every change of stock is a move: a receipt, a transfer between locations, a use, a disposal or a count correction. Moves are never edited; a mistake is corrected by another move. |
| Value         | Stock is valued at the purchase price of its lot. There are no accounting entries.                                                             |

## Use

| Rule              | Description                                                                                                                              |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Usual use         | Each testing method states how much of each item one test uses.                                                                           |
| Automatic use     | Entering a result deducts the method's usual use from the lot with the earliest usable date in the department's locations. The lab QA can change the lot and quantity. |
| Use by hand       | Other uses, such as calibration, a spare part in a machine service or a broken container, are recorded by hand with a reason.           |
| Lots per result   | The moves of a result show which lots it used, for traceability.                                                                          |
| Usable date       | A lot is usable until its expiry date or, once opened, until its opening date plus the item's shelf life after opening, whichever comes first. |
| Expired lots      | A lot past its usable date is expired: it cannot be used and is listed for disposal.                                                      |

## Alerts

| Rule            | Description                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------- |
| Below minimum   | When the stock of an item falls below its minimum quantity, a warning is raised and a purchase is suggested.         |
| Expiring soon   | Lots whose usable date is within a number of days, a system parameter, are listed and notified.                     |
| Expired         | Lots that expire are marked expired by a scheduled job and notified.                                                |
| Who is warned   | The roles and departments notified of each warning are configured by the administrator ([SH-11](../shared.md#sh-11-schedules-and-reminders)); by default the storekeepers. |

## Purchasing

| Rule            | Description                                                                                                                         |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Suppliers       | A supplier is a company contact with a code, a default contact person and the items it sells, with its own references and last prices. |
| Purchase orders | A purchase order to one supplier lists items, quantities and prices. It is signed through its approval chain before it is sent.     |
| Receipts        | Goods that arrive are received against a purchase order, or without one, into a location, with their lot, expiry, quantity, price and certificate. A done receipt creates the lots and moves. |
| Received amount | A purchase order is partially received or received from the quantities its receipts brought in.                                     |

## Actors

- [Storekeeper](features/storekeeper.md): items, locations, suppliers, purchase orders, receipts, transfers and disposal

## Related documents

- [Overview](../index.md)
- [Module boundaries](../../business/module-boundaries.md)
- [Laboratory administrator](../laboratory_module/features/admin.md)
- [Shared technical features](../shared.md)
