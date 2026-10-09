# Features of: Storekeeper

The storekeeper (thủ kho) runs the laboratory's stock: items, locations and suppliers, purchase orders, receipts, transfers, and the disposal of expired lots.

## I. User stories

### Catalog

- **US-SK01** As a storekeeper, I want to maintain stock items with their unit, minimum quantity and shelf life after opening, so that stock is counted and checked the same way every time.
- **US-SK02** As a storekeeper, I want to maintain the tree of stock locations with their storage conditions, so that everyone knows where stock is and how it is kept.
- **US-SK03** As a storekeeper, I want to maintain suppliers with the items they sell, their references and last prices, so that I know where to buy each item.

### Buying

- **US-SK04** As a storekeeper, I want to create a purchase order for a supplier and send it for approval, so that stock is bought only once it is approved.
- **US-SK05** As a storekeeper, I want to send an approved purchase order to the supplier, so that the goods are on their way.
- **US-SK06** As a storekeeper, I want to receive goods against a purchase order, or without one, with their lot, expiry, quantity, price and certificate, so that stock and lots are on record.

### Stock

- **US-SK07** As a storekeeper, I want to move stock between locations, so that the system shows where every lot is.
- **US-SK08** As a storekeeper, I want to record a use or correct a quantity with a reason, so that stock on hand matches what is on the shelf.
- **US-SK09** As a storekeeper, I want to see expired lots and dispose of them, so that nobody uses an expired chemical.
- **US-SK10** As a storekeeper, I want to see stock on hand and its value per item, lot and location, so that I know what the laboratory holds.
- **US-SK11** As a storekeeper, I want to do a stock take of a location as one document and have the differences corrected, so that stock on hand matches the shelves.

## II. Feature details

### 1. Catalog (US-SK01 to US-SK03)

Follows [Stock](../overview.md#stock) and [Purchasing](../overview.md#purchasing).

| Rule      | Description                                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------ |
| Codes     | Items and suppliers get a code from a sequence when none is typed. A typed code must still be unique.        |
| Archiving | Follows [Archiving and deleting](../../../business/archiving-and-deleting.md).                               |

Acceptance criteria:

- An item without a code gets one from its sequence.
- A chemical item stocks exactly one Laboratory chemical, and a chemical is stocked by at most one item.
- An item with stock on hand cannot be archived; the message lists the locations that hold it.

### 2. Buying (US-SK04 to US-SK06)

| Rule      | Description                                                                                                                  |
| --------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Approval  | A purchase order is signed through its approval chain, which the administrator configures, before it can be sent.            |
| Receiving | A receipt creates the lots and moves of what arrived and updates how much of each order line has been received.              |

Acceptance criteria:

- A purchase order cannot be sent before its approval chain has signed it.
- Receiving part of an order sets it to partially received; receiving the rest sets it to received.
- Receiving a chemical creates its lot with the printed expiry date and attaches the certificate.

### 3. Stock (US-SK07 to US-SK11)

Follows [Use](../overview.md#use) and [Alerts](../overview.md#alerts).

| Rule     | Description                                                                                         |
| -------- | --------------------------------------------------------------------------------------------------- |
| Moves    | Every transfer, use, disposal or correction is a move with a reason; moves are never edited.        |
| Disposal | Disposing of an expired lot moves its remaining stock out of every location.                        |

Acceptance criteria:

- A transfer moves the quantity from one location to the other and leaves the total unchanged.
- An expired lot appears in the disposal list and cannot be chosen for a use.
- Stock value per item equals the quantity of each lot times its purchase price.
- Starting a stock take lists every item, lot and location inside its location with its expected quantity.
- Finishing a stock take creates one correction move for each line whose found quantity differs from the expected one, and none for the others.

## III. Related documents

- [Inventory overview](../overview.md)
- [Shared technical features](../../shared.md)
