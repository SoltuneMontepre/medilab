# Conceptual model

The business concepts of Laboratory, E-commerce, Inventory and scheduling. Names follow the [glossary](../glossaries.md); detailed rules belong to the actor features and [business flows](business-flows.md). The [Prisma diagrams](../infrastructure/readme.md) draw Odoo tables and are updated with the implementation through the [database-diagram workflow](../workflows/syncing-database-diagram.md).

## Model scope

Medilab Sync belongs to the product but is outside this conceptual model. Technical concepts and attribute-level details are omitted: audit entries, notification and email messages, notification preferences, signing certificates, portal accounts, roles, document versions and signed PDFs. Portal identities belong to Customer or Person at this level.

Unit categories are part of MeasurementUnit, parameter prices part of TestParameter, and subcontract costs part of ParameterMethod. Invoicing and payments are described in the E-commerce specifications. Service-package membership and chemical consumption are many-to-many relationships. Each RegulationLimit belongs to one Regulation, TestParameter and SampleType; that combination is unique and its limit is not shared across sample types.

## Catalog and laboratory work

```mermaid
erDiagram
    SAMPLE_TYPE o|--o{ SAMPLE_TYPE : broadens
    TEST_PARAMETER }o--o{ PARAMETER_GROUP : belongs_to
    TEST_PARAMETER ||--o{ PARAMETER_METHOD : has
    PARAMETER_METHOD }o--|| TESTING_METHOD : uses
    PARAMETER_METHOD }o--o| DEPARTMENT : performed_in_house_by
    PARAMETER_METHOD }o--o| SUBCONTRACTOR : performed_externally_by
    PARAMETER_METHOD }o--o{ SAMPLE_TYPE : explicitly_applies_to
    TESTING_METHOD ||--o{ SAMPLING_REQUIREMENT : needs
    SAMPLING_REQUIREMENT }o--|| SAMPLE_TYPE : for
    TESTING_METHOD }o--o{ CHEMICAL : consumes
    ACCREDITATION_CERTIFICATE ||--|{ ACCREDITATION_SCOPE_LINE : contains
    ACCREDITATION_SCOPE_LINE }o--|| TESTING_METHOD : covers
    ACCREDITATION_SCOPE_LINE }o--|{ TEST_PARAMETER : covers
    ACCREDITATION_SCOPE_LINE }o--|{ SAMPLE_TYPE : covers
    REGULATION }o--o{ SAMPLE_TYPE : applies_to
    REGULATION ||--o{ REGULATION_LIMIT : defines
    REGULATION_LIMIT }o--|| TEST_PARAMETER : for
    REGULATION_LIMIT }o--|| SAMPLE_TYPE : for
    CUSTOMER ||--o{ TEST_REQUEST : requests
    TEST_REQUEST ||--|{ SAMPLE : includes
    TEST_REQUEST ||--o{ SAMPLE_COLLECTION : receives_through
    SAMPLE_COLLECTION }o--o{ SAMPLE : records_actual_handover
    SAMPLE }o--|| SAMPLE_TYPE : has_type
    SAMPLE }o--o| REGULATION : optionally_compares_against
    SAMPLE ||--|{ SAMPLE_TEST : carries
    SAMPLE_TEST }o--|| PARAMETER_METHOD : uses_from_creation
    SAMPLE_TEST ||--o{ TEST_RESULT : has_results
    SAMPLE ||--o{ SAMPLE_RETURN : is_returned_through
    TEST_REQUEST ||--o{ TEST_REPORT : reports
    REPORT_TEMPLATE ||--o{ TEST_REPORT : prepares
```

| Relationship | Rule |
| --- | --- |
| Way and sample type | A way has one parameter, method and performing party. Explicit applicability gives the unit, optional LOD/LOQ and display precision for one sample type. Each offered parameter and sample type has one default. Technical applicability does not inherit. |
| Sampling | A method's sample-type requirement gives amount, container and preservation. Compatible container and preservation groups share a physical sample and their amounts add. Expected objects per type are the largest line quantity; objects times groups gives expected samples. Collection records the actual handover and customer confirmation. |
| Accreditation | A sample test is accredited only when its in-house way's method, parameter and sample type or ancestor match a valid certificate scope line. A method outside accreditation can still be used. |
| Regulation | Comparison is optional. Scope includes descendants; limits are explicit per regulation, parameter and sample type and never inherited. The selected method, such as a TCVN, determines how to test; a QCVN determines requested comparisons. |
| Result | Each result keeps its unit and LOD/LOQ snapshot and any exact sample-type regulation limit snapshot. It belongs to exactly one booking or subcontract dispatch; a retest is a new result with a new booking. |
| Sample return | A return records what was returned to the customer, when, by whom and to whom. Returning extra samples or excess material leaves the sample's state unchanged; returning a retained sample after its retention period ends it as returned. |
| Report preparation | A report uses one template version and approved business data to create its internal draft. Approval binds the saved draft, result versions and prepared PDF; issued files stay unchanged. Template versions and working files are omitted at this conceptual level. |

## Bookings and people

```mermaid
erDiagram
    DEPARTMENT ||--o{ PERSON : contains
    PERSON }o--o{ TEST_PARAMETER : authorized_by_lab_head_for
    SAMPLE_TEST ||--o{ MACHINE_BOOKING : is_booked_in
    MACHINE_BOOKING }o--|| PERSON : performed_by
    MACHINE_BOOKING }o--o| MACHINE : uses_if_required
    MACHINE }o--o{ TESTING_METHOD : has_duration_and_capacity_for
    MACHINE_BOOKING }o--o{ LOCATION : reserves_step_intervals
    MACHINE_BOOKING o|--o{ TEST_RESULT : measures
    PLAN_REVISION }o--|{ MACHINE_BOOKING : moves
    PLAN_REVISION }o--|{ DEPARTMENT : approved_by_head_of
    SUBCONTRACT_DISPATCH o|--o{ TEST_RESULT : carries
    SUBCONTRACT_DISPATCH }o--|| SUBCONTRACTOR : sends_to
    MACHINE ||--o{ MACHINE_SERVICE : has
    PERSON ||--o{ OVER_TIME : has_planned
    SAMPLE_COLLECTION }o--|| PERSON : collected_by
```

Mermaid ER notation cannot express the exclusive ownership of a result: each `TEST_RESULT` belongs to exactly one `MACHINE_BOOKING` or one `SUBCONTRACT_DISPATCH`, never both or neither, as the Result rule above requires.

A booking has one sample test, one tester and one interval, and a machine only when the way needs one. Bookings whose ways use the same testing method share a machine for exactly the same interval, up to the capacity in samples of the machine-and-method link; a way that needs no machine has its own duration and capacity, 1 by default. Each department's plan proposes bookings for its received, not-started sample tests. A plan revision moves scheduled bookings once the head of each affected department approves its moves, and holds back a move that would miss a committed return date until the customer agrees. Staff shifts and approved leave come from HR; service records supply machine downtime. OverTime records a planned outside-hours interval and reason the head enters for a tester, without payroll or actual-hours confirmation.

The Lab Head configures person-to-parameter authorization indefinitely, without start or expiry dates. The Head of Department assigns work and approves results, including their own entries. The Lab Head reviews the results and signs reports. A result correction and its affected issued report have linked change requests, and a replacement report needs fresh approval and signing before issue.

## Commerce and inventory

```mermaid
erDiagram
    CUSTOMER ||--o{ CONTACT_PERSON : has
    SUBCONTRACTOR ||--o{ CONTACT_PERSON : has
    CUSTOMER ||--o{ SALE_ORDER : places
    SALE_ORDER ||--|{ ORDER_LINE : selects
    ORDER_LINE }o--|| SAMPLE_TYPE : for
    ORDER_LINE ||--|{ ORDER_LINE_SELECTION : retains
    ORDER_LINE_SELECTION }o--|| TEST_PARAMETER : for
    ORDER_LINE_SELECTION }o--|| PARAMETER_METHOD : chooses
    ORDER_LINE }o--o| SERVICE_PACKAGE : buys_whole
    SERVICE_PACKAGE }o--o{ TEST_PARAMETER : contains
    SALE_ORDER ||--o{ QUOTATION : offers
    SALE_ORDER ||--o| TEST_REQUEST : creates
    CUSTOMER ||--o{ ORDER_TEMPLATE : reuses
    SALE_ORDER ||--o| FEEDBACK : receives
    CHEMICAL }o--|| MEASUREMENT_UNIT : measured_in
    CHEMICAL ||--o{ INTERNAL_MOVEMENT : moves
    INTERNAL_MOVEMENT }o--|| STOCK_LOCATION : goes_to
```

An order line contains a parameter or a whole package, with a sample type and quantity. Its selections retain one parameter and its selected or resolved default way per included parameter: one selection for a parameter line and one for every parameter in a package line. Each quotation version keeps those selections; later catalog membership or default changes do not rewrite the accepted version. Sample tests use its retained selections. A package line keeps the package price. Accepted ways change only through a revised quotation and customer agreement. Templates have no price of their own. Completed orders, quotations, results and reports use change requests.

## Related documents

- [Overview](index.md)
- [Laboratory overview](laboratory_module/overview.md)
- [E-commerce overview](ecommerce_module/overview.md)
- [Inventory overview](inventory_module/overview.md)
- [Glossaries](../glossaries.md)
