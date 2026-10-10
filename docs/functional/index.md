# Overview

## About the project

Medilab is a laboratory management system built on Odoo 20 Community and the Odoo apps it already offers, such as Employees, Calendar, Sales, Invoicing and Inventory; it needs no Odoo Enterprise app. It is designed to help laboratories manage their laboratory testing processes efficiently. The system provides a comprehensive solution for managing sales, inventory, and laboratory operations.

Each installation serves one laboratory company; there is no multi-company setup. The system serves laboratories testing in four sectors: food (thực phẩm), cosmetics (mỹ phẩm), pharmaceuticals (dược phẩm) and environment (môi trường).

## Modules

MediLab is split into three modules that can each be installed from the Odoo marketplace and support each other: **E-commerce**, **Inventory** and **Laboratory Testing (core)**. Each module is designed to handle specific aspects of laboratory management, allowing users to customize their experience based on their needs.

[E-commerce Module](./ecommerce_module/overview.md): The E-commerce module allows users to manage their laboratory sales processes, including creating and managing sales orders, invoices, quotations, and customer information. It also provides tools for tracking sales performance and generating reports.

[Inventory Module](./inventory_module/overview.md): The Inventory module provides tools for managing laboratory inventory, including tracking chemical stock levels, managing expiration dates, managing internal movement of materials, and generating reports on inventory performance. It also allows users to manage suppliers.

[Laboratory Module](./laboratory_module/overview.md): The Laboratory module is the core of the system, providing functionality for managing laboratory tests, samples, and results. It includes features for creating and managing parameters, testing procedures, tracking sample progress, and generating reports on testing activities.

It also includes a set of shared technical features that are used by all modules, see [Shared Technical Features](./shared.md).

## Documents

- [Shared technical features](shared.md): requirements shared by all modules and external integrations
- E-commerce module
  - [Overview](ecommerce_module/overview.md)
  - Actors: [Customer](ecommerce_module/features/customer.md), [Sales](ecommerce_module/features/sales.md), [Accountant](ecommerce_module/features/accountant.md), [Admin](ecommerce_module/features/admin.md)
- Inventory module
  - [Overview](inventory_module/overview.md)
  - Actors: [Administrator](inventory_module/features/admin.md), [Storekeeper](inventory_module/features/storekeeper.md), [Team lead](inventory_module/features/team-lead.md), [Tester](inventory_module/features/tester.md)
- Laboratory module
  - [Overview](laboratory_module/overview.md)
  - Actors: [Admin](laboratory_module/features/admin.md), [Sample delivery staff](laboratory_module/features/sample-delivery-staff.md), [Tester](laboratory_module/features/tester.md), [Head of department](laboratory_module/features/head-of-department.md), [Lab head](laboratory_module/features/lab-head.md), [Subcontractor](laboratory_module/features/subcontractor.md)
  - Applications: [Medilab Mobile](laboratory_module/applications/medilab-mobile.md), [Medilab Sync](laboratory_module/applications/medilab-sync.md)
