# Features of: Administrator

To read this document properly, it is considered an add-on or changes compared to the core features of the Laboratory module's admin feature. This actor, of course, inherits all the features of the core admin and all other roles, but in addition, it has some extra features that are specific to the E-commerce module.

please also check: [Admin Core](../../laboratory_module/features/admin.md)

E-commerce keeps prices, taxes and packages in its own tables and does not add columns to Laboratory tables. The tables are drawn in [ecommerce.prisma](../../../infrastructure/database/ecommerce/ecommerce.prisma).

## I. User stories

### Prices and taxes

- **US-AD17** As an administrator, I want to set the price and tax of each test parameter, so that the catalog, cart, quotation and invoice show the same price and tax.
- **US-AD18** As an administrator, I want to maintain taxes and their rates over time, so that each quotation uses the rate in force on its date.
- **US-AD19** As an administrator, I want to record what each subcontractor charges per test, so that margin can be reported for subcontracted work.

### Service packages

- **US-AD20** As an administrator, I want to maintain service packages with their parameters, quantities, price and tax, so that customers can order common sets of tests at one price.

## II. Feature details

### 1. Prices and taxes (US-AD17 to US-AD19)

| Rule               | Description                                                                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Parameter price    | A parameter has one price, excluding VAT, the same whichever method tests it, whichever sample type it is tested on and whether a subcontractor tests it. Groups do not set a price. |
| Tax                | Every parameter price and package has one tax, such as VAT 10% or not subject to VAT. Tax is added on quotations and invoices, never in the cart.         |
| Tax rate over time | A tax's rate is recorded with the period it applies, so a rate change, such as a temporary VAT reduction, is a new period. The periods of one tax do not overlap. A quotation uses the rate in force on its date, and its invoices use the quotation's rates. |
| Currency           | All prices are in VND.                                                                                                                                   |
| Special prices     | There are no customer price lists. Special prices, such as for partners or promotions, are discounts sales gives on the quotation.                     |
| Tax on a quotation | A quotation line takes the tax of its parameter or package. Sales can change it on the quotation, such as 0% for a foreign customer.                    |
| Subcontractor cost | Each subcontracted pair of parameter and method records what the subcontractor charges per test, excluding VAT, for margin reporting.                   |
| Archiving and deleting | Follows [Archiving and deleting](../../../business/archiving-and-deleting.md). Parameter prices, taxes and subcontract costs can be archived or deleted; a tax's rates are deleted with it. |

Acceptance criteria:

- A parameter without a price and tax cannot be added to a cart or quotation.
- A quotation dated during a reduced VAT period shows the reduced rate; one dated after it shows the normal rate.
- An invoice posted after a reduced VAT period ends keeps the reduced rate of its quotation.
- Adding a second rate period that overlaps an existing one for the same tax is refused with a message.
- A tax that an active parameter price or package uses cannot be archived; the message lists them.
- A tax that nothing refers to can be deleted, together with its rates.
- A tax that only finished quotations and invoices use can be archived but not deleted.

### 2. Service packages (US-AD20)

Ordering packages follows [Sales order and customer order](../../../business/sales-order-and-customer-order.md).

| Rule          | Description                                                                                                                       |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Content       | A package holds parameters from any groups, each with a quantity of at least one.                                                 |
| Price         | A package has one price, excluding VAT, and one tax.                                                                              |
| Price warning | When a package's price is higher than the sum of its parameters' own prices times their quantities, the administrator is warned on the package and on the parameter whose price change caused it. |
| Archiving and deleting | Follows [Archiving and deleting](../../../business/archiving-and-deleting.md). A package's lines are deleted with it. |

Acceptance criteria:

- A package cannot hold the same parameter on two lines; the quantity is raised instead.
- Lowering a parameter's price so that a package containing it costs more than its parts shows a warning on that package.
- A package that nothing refers to can be deleted, together with its lines.
- A package on an unfinished quotation cannot be archived; the message lists the quotations.

## III. Related documents

- [Admin Core](../../laboratory_module/features/admin.md)
- [Accountant](accountant.md)
- [Sales order and customer order](../../../business/sales-order-and-customer-order.md)
- [Payment and quotation](../../../business/payment-and-quotation.md)
- [Database diagram](../../../infrastructure/database/ecommerce/ecommerce.prisma)
