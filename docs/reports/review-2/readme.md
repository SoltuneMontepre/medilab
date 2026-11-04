# Review 2 diagrams

The context diagram, use case diagrams, system activity diagram and system overview shown at Review 2 of capstone project FA26SE294. They are drawn from the current documents in `docs/`; where those documents differ from the [capstone proposal](../proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx), the difference is listed under [Warnings](#warnings).

## Diagrams

| File                                                                                                                                                                                            | Shows                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [context-diagram.drawio](context-diagram.drawio), [SVG](context-diagram.svg)                                                                                                                    | MediLab as one process with 13 external entities and 73 data flows (DFD level 0)                                                                                          |
| [use-case-diagram.drawio](use-case-diagram.drawio), SVG pages [1](use-case-diagram-1.svg), [2](use-case-diagram-2.svg), [3](use-case-diagram-3.svg)                                             | 71 use cases in three areas: orders, quotations and payments; samples, testing and outsourcing; laboratory management and setup                                           |
| [System activity diagram](system-activity-diagram.md), [system-activity-diagram.drawio](system-activity-diagram.drawio), [SVG](system-activity-diagram.svg), [PDF](system-activity-diagram.pdf) | The core flows WF-01 to WF-06 and the supporting flows SF-01 to SF-11 of [business flows](../../functional/business-flows.md) merged as written into one swimlane diagram |
| [system-overview.png](system-overview.png)                                                                                                                                                      | Client applications, ingress, core services, storage and external services, with their protocols                                                                          |

## Modelling rules

- **Actors** are named as in the [glossaries](../../glossaries.md): Customer, Sales, Head of Sales, Accountant, Sample Delivery Staff, Tester, Head of Department, Lab Head, Administrator and Subcontractor. A visitor who orders without signing in and a business customer's contact person are drawn as Customer.
- **External systems** carry generic names: Payment Gateway, Email Service and Digital Signature Provider. The provider behind each is named only in [External systems](#external-systems).
- **Not drawn:** the Inventory and Onboarding modules and their actors, the Auditor, a backup signer given a top-level role for a limited time, the public report verification page, Medilab Mobile and mobile push notifications, and the IoT devices with their MQTT broker.
- **Use cases** follow the feature sections of each actor document; [Use case sources](#use-case-sources) maps each to its user stories. Head of Sales inherits every Sales use case.
- **Activity diagram:** the 17 diagrams of business flows merged as written, with their lanes and wording; flows are joined only where business-flows.md names the connection, and steps the source draws outside every lane sit in the MediLab lane.

## External systems

| Diagram name               | Provider     | Purpose                                                                        | Data sent                                                                         | Source                                                                                                                            |
| -------------------------- | ------------ | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Payment Gateway            | PayOS        | Online payment of advance and final invoices; daily reconciliation             | Payment requests with order and amount; receives payment results and transactions | [Shared features](../../functional/shared.md#2-payos-payments), [PayOS](../../specs/payos.md)                                     |
| Email Service              | Brevo        | Notifications, quotations, invoices and issued reports by e-mail               | E-mails and their attachments to customers and staff                              | [Shared features](../../functional/shared.md#1-brevo-email)                                                                       |
| Digital Signature Provider | Viettel Sign | Digitally signs the approved test report PDF with the laboratory's certificate | The prepared report PDF; receives the signed PDF                                  | [Shared features](../../functional/shared.md#3-viettel-sign-digital-signature), [Digital signing](../../specs/digital-signing.md) |

## Warnings

Differences between the current documents and the capstone proposal. The diagrams follow the documents.

| #   | Topic                     | Proposal                                                                                 | Documents                                                                                                                                          | In the diagrams                                       |
| --- | ------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| W1  | Mobile application        | Deliverable 4, mobile access for permitted operations and push as a notification channel | Medilab Mobile is deferred ([overview](../../functional/index.md))                                                                                 | Not drawn                                             |
| W2  | Head of Sales             | No such actor; Sales reviews and confirms quotations                                     | Head of Sales sets approval thresholds, approves quotations above them and cancellations after collection, and allows customers to order on credit | Drawn as an actor that inherits Sales                 |
| W3  | Inventory and Onboarding  | Chemicals are master data only; no store or onboarding                                   | Inventory and Onboarding modules with Storekeeper, Team lead and supplier work                                                                     | Not drawn                                             |
| W4  | Test request at reception | Sampling staff create test requests at reception                                         | With E-commerce, every test request comes from an order; Sales creates the order for a walk-in customer (WF-01-A1)                                 | Reception starts from a confirmed order               |
| W5  | Result signatures         | Testers and heads apply a digital signature to results                                   | Approving is signing in the system; only the test report PDF is signed by the provider (SH-04)                                                     | Digital Signature Provider serves report signing only |
| W6  | Subcontractor results     | The department head records subcontractor results                                        | The subcontractor (US-SUB02) or a tester (US-T09) enters them; the head approves                                                                   | Entered by Subcontractor or Tester                    |
| W7  | Online editing            | Not listed                                                                               | Reports and result spreadsheets are edited in ONLYOFFICE (WF-04-A8, WF-06)                                                                         | Shown in the system overview                          |
| W8  | IoT devices               | Not listed                                                                               | The architecture deploys an MQTT broker for IoT environment monitors                                                                               | Not drawn                                             |
| W9  | Audit trail reader        | The administrator views audit trails                                                     | An Auditor role reads the audit trail ([audit trail](../../specs/audit-trail.md))                                                                  | Not drawn                                             |
| W10 | Laboratory files API      | FastAPI                                                                                  | Native Odoo HTTP controllers ([decision](../../decisions/laboratory-files-architecture.md))                                                        | FastAPI removed                                       |
| W11 | Object storage            | MinIO and Cloudflare R2                                                                  | S3 buckets from the VPS provider ([architecture](../../infrastructure/architecture.md#object-storage))                                             | Shown as S3 storage                                   |

The Review 2 Design Brief of 22 October also differs from the current documents:

| #   | Topic        | Design Brief                                                                                 | Documents                                                                                                                                    |
| --- | ------------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| W12 | Project name | Laboratory Information Management Subsystem for Contract Testing Laboratory on Odoo Platform | The proposal: Design and Development of a Laboratory Information Management Subsystem for a Contract Testing Laboratory on the Odoo Platform |
| W13 | WF-01        | "Order to approved test request": the Head of Sales signs after payment                      | "Order to confirmed test request": the Head of Sales approves a quotation above the thresholds before it is sent                             |
| W14 | F-15         | Sample delivery staff create test requests                                                   | With E-commerce, every test request comes from an order                                                                                      |

## Use case sources

| Diagram              | Actor                      | Use case                                 | Source                             |
| -------------------- | -------------------------- | ---------------------------------------- | ---------------------------------- |
| Commerce             | Customer                   | Manage account and profile               | US-C01 to US-C06                   |
| Commerce             | Customer                   | Configure notifications                  | US-C07                             |
| Commerce             | Customer                   | Place order                              | US-C08 to US-C10, US-C22           |
| Commerce             | Customer                   | Cancel order or request cancellation     | US-C11, US-C12                     |
| Commerce             | Customer                   | Accept or decline quotation              | US-C13, US-C15                     |
| Commerce             | Customer                   | Track orders and download reports        | US-C18, US-C19                     |
| Commerce             | Customer                   | Download invoices and receipts           | US-C16                             |
| Commerce             | Customer                   | Contact support and give feedback        | US-C20, US-C21                     |
| Commerce             | Customer                   | Pay online                               | US-C14, US-C17                     |
| Commerce             | Accountant                 | Reconcile online payments                | US-A13                             |
| Commerce             | Accountant                 | Confirm or reject recorded payment       | US-A07, US-A08                     |
| Commerce             | Accountant                 | Track payment status                     | US-A06, US-A09 to US-A12           |
| Commerce             | Accountant                 | View financial reports                   | US-A14 to US-A16                   |
| Commerce             | Accountant                 | Manage invoices                          | US-A01 to US-A05                   |
| Commerce             | Head of Sales              | Approve quotation above threshold        | WF-01, SH-04                       |
| Commerce             | Head of Sales              | Approve cancellation after collection    | US-S17, SF-02                      |
| Commerce             | Head of Sales              | Set thresholds and credit terms          | WF-01-A5, Sales credit gate        |
| Commerce             | Sales                      | Manage customers                         | US-S03, US-S04, US-S24             |
| Commerce             | Sales                      | Claim or create order                    | US-S01, US-S02                     |
| Commerce             | Sales                      | Estimate return date                     | US-S21, US-S22                     |
| Commerce             | Sales                      | Manage order templates                   | US-S09                             |
| Commerce             | Sales                      | Confirm order and start collection       | US-S12, US-S15                     |
| Commerce             | Sales                      | Record customer payment                  | US-S11                             |
| Commerce             | Sales                      | Handle cancellation                      | US-S16, US-S17                     |
| Commerce             | Sales                      | Track orders and performance             | US-S18, US-S19                     |
| Commerce             | Sales                      | Answer support requests                  | US-S20                             |
| Commerce             | Sales                      | Prepare and send quotation               | US-S05 to US-S08, US-S10           |
| Commerce             | Payment Gateway            | Pay online                               | Secondary actor                    |
| Commerce             | Payment Gateway            | Reconcile online payments                | Secondary actor                    |
| Commerce             | Email Service              | Manage invoices                          | Secondary actor                    |
| Commerce             | Email Service              | Prepare and send quotation               | Secondary actor                    |
| Laboratory work      | Sample Delivery Staff      | Collect samples                          | US-SD01 to US-SD05                 |
| Laboratory work      | Sample Delivery Staff      | Receive and label samples                | US-SD07 to US-SD10                 |
| Laboratory work      | Sample Delivery Staff      | Put insufficient sample on hold          | US-SD11                            |
| Laboratory work      | Sample Delivery Staff      | Hand samples to departments              | US-SD12                            |
| Laboratory work      | Sample Delivery Staff      | Carry dispatches to subcontractor        | US-SD13                            |
| Laboratory work      | Sample Delivery Staff      | Return samples to customer               | US-SD15                            |
| Laboratory work      | Sample Delivery Staff      | Deliver test reports                     | US-SD14                            |
| Laboratory work      | Tester                     | Claim testing task                       | US-T01                             |
| Laboratory work      | Tester                     | Accept, move or cancel booking           | US-T02 to US-T04, US-T19 to US-T21 |
| Laboratory work      | Tester                     | View method steps                        | US-T17, US-T18                     |
| Laboratory work      | Tester                     | Enter and send result                    | US-T05 to US-T07, US-T22           |
| Laboratory work      | Tester                     | Retest rejected result                   | US-T08                             |
| Laboratory work      | Tester                     | Enter subcontractor result               | US-T09                             |
| Laboratory work      | Tester                     | Raise change request                     | US-T11                             |
| Laboratory work      | Tester                     | Sync and version lab files               | US-T23 to US-T27                   |
| Laboratory work      | Tester                     | Share and browse folders                 | US-T28, US-T29                     |
| Laboratory work      | Tester                     | Dispose of retained samples              | US-T10                             |
| Laboratory work      | Head of Department         | Assign testing tasks                     | US-HD01, US-HD02                   |
| Laboratory work      | Head of Department         | Manage department schedule               | US-HD03, US-HD04, US-HD12, US-HD14 |
| Laboratory work      | Head of Department         | Record department sample receipt         | US-HD06                            |
| Laboratory work      | Head of Department         | Request more sample                      | US-HD07                            |
| Laboratory work      | Head of Department         | Approve or reject result                 | US-HD08                            |
| Laboratory work      | Head of Department         | Cancel sample test                       | US-HD09                            |
| Laboratory work      | Head of Department         | Outsource tests                          | US-HD05, US-HD10, US-HD11, US-HD13 |
| Laboratory work      | Head of Department         | Create sample folders                    | US-HD15                            |
| Laboratory work      | Head of Department         | Sign result file version                 | US-HD16                            |
| Laboratory work      | Head of Department         | View department statistics               | US-HD18                            |
| Laboratory work      | Subcontractor              | View dispatches                          | US-SUB01                           |
| Laboratory work      | Subcontractor              | Enter outsourced results                 | US-SUB02                           |
| Laboratory work      | Email Service              | Deliver test reports                     | Secondary actor                    |
| Management and setup | Lab Head                   | Authorize testers per parameter          | US-LH04                            |
| Management and setup | Lab Head                   | Approve report change request            | US-LH03                            |
| Management and setup | Lab Head                   | View laboratory statistics               | US-LH06                            |
| Management and setup | Lab Head                   | Sign or reject test report               | US-LH01, US-LH02, US-LH05          |
| Management and setup | Administrator              | Manage testing catalog                   | US-AD01 to US-AD06, US-AD26        |
| Management and setup | Administrator              | Manage regulations and limits            | US-AD07                            |
| Management and setup | Administrator              | Manage accreditations and dossiers       | US-AD08, US-AD28                   |
| Management and setup | Administrator              | Manage locations                         | US-AD27                            |
| Management and setup | Administrator              | Manage machines and chemicals            | US-AD09 to US-AD11                 |
| Management and setup | Administrator              | Manage subcontractors                    | US-AD12, US-AD19                   |
| Management and setup | Administrator              | Manage people, roles and approval chains | US-AD13 to US-AD16                 |
| Management and setup | Administrator              | Manage prices, taxes and packages        | US-AD17, US-AD18, US-AD20          |
| Management and setup | Administrator              | Administer folders and devices           | US-AD29 to US-AD31                 |
| Management and setup | Administrator              | Manage report templates                  | US-AD36                            |
| Management and setup | Administrator              | Configure settings                       | SH-03                              |
| Management and setup | Digital Signature Provider | Sign or reject test report               | Secondary actor                    |

## Related documents

- [Reports](../readme.md)
- [Business flows](../../functional/business-flows.md)
- [Glossaries](../../glossaries.md)
- [Architecture](../../infrastructure/architecture.md)
