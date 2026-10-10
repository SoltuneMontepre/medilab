# Module boundaries

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- Customers, tasks and schedules belong to Laboratory, so they work without E-commerce. E-commerce keeps prices, taxes, service packages and each customer's sales terms.
- Machines and chemical information belong to Laboratory. Departments and their teams belong to Laboratory. Inventory manages stock, stores, containers and their expiry, movement between stores, recipes, suppliers and purchasing, cost centres and budgets, how much of each item one test of a method uses, and which containers and lots each test result used.

## Odoo apps

MediLab is built on the apps of Odoo Community and extends them; it does not rebuild what they already do.

- A module depends only on Odoo Community apps, OCA modules and the MediLab modules above. No module depends on Odoo Enterprise, so every module installs on a free Odoo.
- An OCA module is used only once its Odoo 20 version is released as installable. Until then the feature is built on Odoo Community alone.
- When an Odoo app has the concept, MediLab extends its model with `_inherit` and its views, instead of adding a model of its own. A MediLab model is added only for what no app holds, such as samples and results.

| Module     | Odoo apps it depends on                                                                                     |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| Laboratory | `mail`, `hr`, `resource`, `calendar`, `project`, `maintenance`, `uom`, `portal`                             |
| E-commerce | `sale_management`, `website_sale`, `account_payment`, `account_debit_note`, `l10n_vn`, `rating`             |
| Inventory  | `stock`, `stock_account`, `product_expiry`, `purchase_stock`, `mrp`                                         |

Each module also has every app its own apps depend on, such as `bus` through `mail` and `account` through `sale_management`.

### What each concept is built on

| Concept                                   | Built on                                                                                                                                               |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Department, team                          | `hr.department`; a team is a department whose parent is its department                                                                                 |
| Person                                    | `hr.employee`, with their Odoo user and work contact                                                                                                   |
| Role                                      | A MediLab role holding permissions, each with its Odoo role (`res.role`) whose users are the role's holders                                            |
| Permission                                | A MediLab permission generating an Odoo group (`res.groups`) and access (`ir.access`), see [Permissions](../specs/permissions.md)                      |
| Customer, subcontractor, supplier         | `res.partner`, with the customer and subcontractor details MediLab keeps for it                                                                        |
| Measurement unit                          | `uom.uom`; units that convert into each other share a reference unit                                                                                   |
| Machine                                   | `maintenance.equipment`                                                                                                                                |
| Calibration, maintenance, repair          | `maintenance.request`                                                                                                                                  |
| Task, to-do list, department queue        | `project.task`; each department has a project holding its queue                                                                                        |
| Personal schedule, reminders              | `calendar.event` with its alarms, for planned tasks and machine bookings; working hours from `resource.calendar`                                       |
| Notifications in the application, e-mail  | `mail.message` and `mail.notification` with pop-ups on `bus`; e-mail through Brevo as Odoo's outgoing mail server                                      |
| Notification event                        | `mail.message.subtype`                                                                                                                                 |
| Scheduled job                             | `ir.cron`, with its progress (`ir.cron.progress`) and failure count                                                                                    |
| Files, photos, signed PDFs, archive files | `ir.attachment`                                                                                                                                        |
| Settings, numbering, languages            | `res.config.settings` and `ir.config_parameter`, `ir.sequence`, `res.lang` with Odoo's translations                                                    |
| Customer portal, shop                     | `portal`, and `website_sale` for the public catalog and cart                                                                                           |
| Test parameter or package for sale        | `product.template` of type service for a parameter; a service package is a combo product                                                               |
| Price, customer sales terms               | The product's sales price; the customer contact's payment terms (`account.payment.term`) and credit limit. There are no customer price lists          |
| Tax                                       | `account.tax`                                                                                                                                          |
| Order, cart, quotation                    | `sale.order`; the cart is the `website_sale` cart; each sent quotation is kept as a MediLab revision with its PDF                                     |
| Order template                            | `sale.order.template`                                                                                                                                  |
| Invoice, advance and adjustment invoice   | `account.move`: an advance invoice is a down payment invoice, an adjustment invoice is a credit or debit note                                          |
| Payment, receipt, payment link            | `account.payment`, `payment.transaction`; PayOS is a payment provider (`payment.provider`); a bank transfer is paid from the invoice's VietQR code (`l10n_vn`)                                                             |
| Support conversation                      | Odoo messages on the MediLab support request, from the back office and the portal                                                                     |
| Feedback                                  | `rating.rating`                                                                                                                                        |
| Stock item, chemical in stock             | `product.product`, storable                                                                                                                            |
| Store, location                           | `stock.location`; a store is a location with a holder and a manager                                                                                    |
| Lot, expiry                               | `stock.lot` with the dates of `product_expiry`                                                                                                         |
| Container                                 | `stock.package` holding the quantity of one lot                                                                                                        |
| Minimum quantity                          | `stock.warehouse.orderpoint`                                                                                                                           |
| Stock on hand, move                       | `stock.quant`, `stock.move`                                                                                                                            |
| Requisition, transfer, receipt            | `stock.picking`                                                                                                                                        |
| Disposal, waste                           | A move to Odoo's scrap location with its scrap reason (`stock.scrap.reason.tag`)                                                                       |
| Stock take                                | Counted quantities on `stock.quant`, grouped by a MediLab stock take                                                                                   |
| Recipe, prepared solution                 | `mrp.bom`, `mrp.production`                                                                                                                            |
| Costing method, stock value               | `stock_account`: first in, first out, or average cost                                                                                                  |
| Cost centre                               | `account.analytic.account`                                                                                                                             |
| Supplier item, purchase order             | `product.supplierinfo`, `purchase.order`                                                                                                               |
| Subcontract cost                          | `product.supplierinfo` of the subcontractor on the parameter's product                                                                                 |

### Menus

People see the Odoo apps with their own menus, and MediLab adds its menus to them. Master data has its own Master Data app, where every installed module adds its master data. Analysis goes under the Reporting menu of the app it is about.

| App                      | MediLab menus                                                                                                                                                                                                                          |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Master Data              | Laboratory: test parameters, parameter groups, sample types, testing fields and methods, units, regulations, quality registrations, machines, chemicals and subcontractors. E-commerce: prices, taxes and service packages. Inventory: stock items, stores and locations, suppliers, recipes and cost centres |
| Laboratory               | Test requests, samples, results, test reports and their analysis under its Reporting menu                                                                                                                                             |
| Tasks                    | The person's day, their tasks and the queues they can claim from                                                                                                                                                                       |
| Odoo's Employees         | People, departments, teams, roles and permissions                                                                                                                                                                                      |
| Odoo's Sales             | E-commerce orders, quotations, invoices, payments, support and sales analysis under its Reporting menu; the shop and portal are on the website                                                                                       |
| Odoo's Inventory         | Stock, moves, requisitions, transfers, receipts, stock takes, charges and stock analysis under its Reporting menu                                                                                                                     |

What no Odoo Community app holds stays MediLab's own: the test catalog, test requests, samples, sample tests and results, test reports, handover records, approval chains and signatures, change requests, machine bookings and the scheduler, subcontract dispatches, task types, the audit trail, document locks, notification preferences and pushes to Medilab Mobile, run logs of scheduled jobs, the samples and quotation revisions of an order, cancellation and support requests, reconciliation days, stock takes, how much each method uses, budgets, stock charges and the accounting export, and digital signing through Viettel Sign.

## Related documents

- [Overview](../functional/index.md)
- [Shared technical features](../functional/shared.md)
- [Database conventions](../conventions/database.md)
