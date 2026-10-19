# Inventory questions

- **Stock takes.** How often does each store do a stock take (kiểm kê kho)? (blocks US-SK11, US-TL04)
- **Changing the charge point.** Stock issued under "on issue" was charged when it entered its store. If the charge point then changes to "on use", should using that stock be charged again, or should the system remember which stock was already charged? (blocks US-AD25)
- **Accounting entries.** Odoo's stock valuation can post journal entries in Odoo Invoicing. The documents send charges to MISA or FAST through the export instead. Should Odoo only value stock, without journal entries, as the documents describe? (blocks US-SK10, US-SK14)
- **Storekeeper of the central store.** The manager of the central store holds the storekeeper role, but roles other than the administrator are user data that no module can name. Should the system check it, for example by the location permissions the manager holds, or is it left to the administrator who sets up the stores? (blocks US-AD21)
- **Archiving what an open purchase order names.** Archiving a record is refused while an unfinished document refers to it, but the item rule lists only stock on hand, use per test and recipes, and a purchase order names its supplier's contact rather than the supplier. Should a supplier or an item on a purchase order that is not fully received or cancelled be refused archiving, listing the orders? (blocks US-SK03, US-SK04)

## Related documents

- [Inventory overview](../docs/functional/inventory_module/overview.md)
