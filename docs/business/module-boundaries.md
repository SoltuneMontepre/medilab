# Module boundaries

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- Customers, tasks and schedules belong to Laboratory, so they work without E-commerce. E-commerce keeps prices, taxes, service packages and each customer's sales terms.
- Machines and chemical information belong to Laboratory. Departments and their teams belong to Laboratory. Inventory manages stock, stores, containers and their expiry, movement between stores, recipes, suppliers and purchasing, cost centres and budgets, how much of each item one test of a method uses, and which containers and lots each test result used.

## Odoo apps

MediLab is built on Odoo Community and extends its apps where they hold a concept the way MediLab needs it; it does not rebuild what they already do.

- A module depends only on Odoo Community apps and the MediLab modules above. No module depends on Odoo Enterprise, so every module installs on a free Odoo.
- A module depends on as few apps as it needs. An app that only brings features MediLab does not use, or a concept that does not fit, is not added; MediLab keeps its own model instead.
- When an app has the concept, MediLab extends its model with `_inherit` and its views, instead of adding a model of its own. A MediLab concept with its own lifecycle, permissions or links, which the app holds only part of, is its own model delegating to the app's record with `_inherits`, as [Database conventions](../conventions/database.md#models) states.

| Module     | Odoo apps it depends on                             |
| ---------- | --------------------------------------------------- |
| Laboratory | `hr`, `portal`, `calendar`                          |
| E-commerce | `sale`, `l10n_vn`, `rating`                         |
| Inventory  | `stock_account`, `product_expiry`, `purchase_stock` |


Each module also has every app its own apps depend on: `mail`, `bus` and `resource` through `hr`; `account`, `account_payment`, `payment` and `product` through `sale`; `account_qr_code_emv` through `l10n_vn`; `stock`, `uom` and `purchase` through Inventory's apps.

### What each concept is built on

| Concept                                   | Built on                                                                                                                                                         |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Department, team                          | `hr.department`; a team is a department whose parent is its department                                                                                           |
| Person                                    | `medilab.person`, delegating to `hr.employee` with `_inherits`: its table holds the team, roles and direct permissions, and the employee the name, user, work contact and department |
| Role, permission                          | MediLab roles and permissions generating Odoo groups (`res.groups`) and accesses (`ir.access`), see [Permissions](../specs/permissions.md)                        |
| Customer, subcontractor, supplier         | `res.partner`, with the customer, subcontractor and supplier details MediLab keeps for it                                                                        |
| Personal schedule, reminders              | `calendar.event`: every planned task and machine booking has one, kept in step both ways with MediLab's task management; its alarm is the reminder               |
| Notifications in the application, e-mail  | `mail.message` and `mail.notification` with pop-ups on `bus`; e-mail through Brevo as Odoo's outgoing mail server                                               |
| Notification event                        | `mail.message.subtype`                                                                                                                                           |
| Files, photos, signed PDFs, archive files | `ir.attachment`                                                                                                                                                  |
| Settings, numbering, languages            | `res.config.settings` and `ir.config_parameter`, `ir.sequence`, `res.lang` with Odoo's translations                                                             |
| Customer portal, shop                     | `portal`, with MediLab's own public catalog, cart and order pages                                                                                                |
| Test parameter or package for sale        | `product.template` of type service for a parameter; a service package is a combo product                                                                        |
| Price, customer sales terms               | The product's sales price; the customer contact's payment terms (`account.payment.term`) and credit limit. There are no customer price lists                     |
| Tax                                       | `account.tax`                                                                                                                                                    |
| Order, cart, quotation                    | `sale.order`; a draft order is the cart; each sent quotation is kept as a MediLab revision with its PDF                                                          |
| Invoice, advance and adjustment invoice   | `account.move`: an advance invoice is a down payment invoice; an adjustment that lowers an invoice is a credit note, one that raises it a new invoice linked to the original |
| Payment, receipt                          | `account.payment`, `payment.transaction`; PayOS is a payment provider (`payment.provider`); a bank transfer is paid from the invoice's VietQR code (`l10n_vn`)  |
| Support conversation                      | Odoo messages on the MediLab support request, from the back office and the portal                                                                               |
| Feedback                                  | `rating.rating`                                                                                                                                                  |
| Stock item, chemical in stock             | `product.product`, storable, counted in a `uom.uom` unit                                                                                                         |
| Store, location                           | `stock.location`; a store is a location with a holder and a manager                                                                                              |
| Lot, expiry                               | `stock.lot` with the dates of `product_expiry`                                                                                                                   |
| Container                                 | `stock.package` holding the quantity of one lot                                                                                                                  |
| Minimum quantity                          | `stock.warehouse.orderpoint`                                                                                                                                     |
| Stock on hand, move                       | `stock.quant`, `stock.move`                                                                                                                                      |
| Requisition, transfer, receipt            | `stock.picking`                                                                                                                                                  |
| Disposal, waste                           | A move to Odoo's scrap location with its scrap reason (`stock.scrap.reason.tag`)                                                                                 |
| Stock take                                | Counted quantities on `stock.quant`, grouped by a MediLab stock take                                                                                             |
| Preparation of a solution                 | Odoo stock moves of the MediLab preparation: its ingredients out of their containers, the solution into a new container                                         |
| Costing method, stock value               | `stock_account`: first in, first out, or average cost                                                                                                            |
| Cost centre                               | `account.analytic.account`                                                                                                                                       |
| Supplier item, purchase order             | `product.supplierinfo`, `purchase.order`                                                                                                                         |
| Subcontract cost                          | `product.supplierinfo` of the subcontractor on the parameter's product                                                                                           |

What no app holds the way MediLab needs it stays MediLab's own: scheduled jobs and their queue on Odoo's cron, the audit trail, approval chains and signatures, the test catalog with its units, machines and their service records, test requests, samples, sample tests and results, test reports, handover records, change requests, tasks and task types, machine bookings and the scheduler, subcontract dispatches, document locks, notification preferences and pushes to Medilab Mobile, the public catalog and cart pages, the samples and quotation revisions of an order, order templates, cancellation and support requests, reconciliation days, recipes and preparations, stock takes, how much each method uses, budgets, stock charges and the accounting export, and digital signing through Viettel Sign.

### Menus

People see the Odoo apps with their own menus, and MediLab adds its menus to them. Master data has its own Master Data app, where every installed module adds its master data. Analysis goes under the Reporting menu of the app it is about.

| App              | MediLab menus                                                                                                                                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Master Data      | Laboratory: test parameters, parameter groups, sample types, testing fields and methods, units, regulations, quality registrations, machines, chemicals and subcontractors. E-commerce: prices, taxes and service packages. Inventory: stock items, stores and locations, suppliers, recipes and cost centres |
| Laboratory       | Test requests, samples, results, test reports and their analysis under its Reporting menu                                                                                                                                             |
| Tasks            | The person's day, their tasks and the queues they can claim from                                                                                                                                                                       |
| Odoo's Calendar  | Each person's planned tasks and machine bookings, next to their other events                                                                                                                                                          |
| Odoo's Employees | People, departments, teams, roles and permissions                                                                                                                                                                                      |
| Odoo's Sales     | E-commerce orders, quotations, order templates, invoices, payments, support and sales analysis under its Reporting menu                                                                                                              |
| Odoo's Inventory | Stock, moves, requisitions, transfers, receipts, preparations, stock takes, charges and stock analysis under its Reporting menu                                                                                                        |

## Related documents

- [Overview](../functional/index.md)
- [Shared technical features](../functional/shared.md)
- [Database conventions](../conventions/database.md)
