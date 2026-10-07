# Docs

Index of the MediLab documentation. Each folder has one purpose; put a new document in the folder that matches it.

## Business rules

Rules every document and every module states and implements the same way. If a document needs to differ from one of these, change the rule here first.

- [Approval and signing chain](approval-and-signing-chain.md): approving is signing, generated documents, locked documents
- [Sales order and customer order](sales-order-and-customer-order.md): ordering by parameter, parameter prices, cancellation
- [Payment and quotation](payment-and-quotation.md): accepting a quotation, VAT
- [Module boundaries](module-boundaries.md): which module owns what

## Conventions

Code conventions for agents and the system.

- [Documentation](conventions/documentation.md): how documents are written and formatted
- [Glossary](conventions/glossary.md): index each new glossary term in the glossaries
- [Translation and menus](conventions/translation.md): Vietnamese and English strings, menu structure
- [Module structure](conventions/module_structure.md): models and views grouped by concern, constants
- [Python](conventions/python.md): tooling, file structure, imports, naming, constants, code rules
- [Database](conventions/database.md): model naming, fields, relationships, constraints
- [Taskfiles](conventions/taskfiles.md): task layout, shell rules, colored output helpers
- [Frontend](conventions/frontend.md)
- [Styling](conventions/styling.md)

## Infrastructure

- [Secrets](infrastructure/secrets.md): Doppler config and the secrets published to GitHub

## Glossaries

- [Glossaries](glossaries.md): shared terms in English and Vietnamese

## Functional

Business domain features, actors and business rules.

- [Overview](functional/index.md): the project and its modules
- [Shared technical features](functional/shared.md): requirements shared by all modules and external integrations
- [E-commerce module](functional/ecommerce_module/overview.md)
- [Laboratory module](functional/laboratory_module/overview.md)
- [Inventory module](functional/inventory_module/overview.md)

## Reports

Everything else: documents, diagrams and supporting material.
