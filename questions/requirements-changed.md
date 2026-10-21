# Requirements changed

Decisions of nnh53 (product owner) that change or extend the documents and Prisma schemas named under each item. The documents are not updated yet. Those of 09-10-2026 and 10-10-2026 were taken while reviewing the conceptual ERD: the StarUML project [ERD-temp.mdj](https://github.com/SoltuneMontepre/medilab-past/blob/main/docs/target-design/erd/ERD-temp.mdj), data model `Conceptual`, 46 entities and 85 relationships. Those of 21-10-2026 were taken while comparing the SEP490 backlog of medilab-past and the [capstone proposal](../docs/reports/readme.md) with the documents.

## Ordering and ways of testing

- **The customer or sales chooses the method.** A customer may choose the way of testing of each parameter in an order, and sales may choose or change it on the quotation until the customer accepts it (21-10-2026). When neither does, the default way of testing is filled in. Every pair of a parameter and a sample type it can be tested on has exactly one default way of testing. Changes the [Laboratory overview](../docs/functional/laboratory_module/overview.md) rule "The way of testing is chosen later by the laboratory", and `parameter_method.is_default`, which is per parameter today.
- **Ways of testing are fixed once accepted.** Once the customer accepts the quotation, nobody changes the way of testing of an order line, whether the customer or sales chose it or it was the default.
- **Only ways of testing the laboratory can perform are offered.** A way of testing is offered when it is active and either:
  - tested in-house, with at least one machine that can run it, in use and within its calibration date, and at least one person authorized for the parameter; or
  - subcontracted, with the subcontractor active and its accreditation not expired.

  When the laboratory cannot perform it, or the machine has a fault, customers cannot choose it.
- **Machine fault after ordering.** The scheduling system moves the test to another machine that can run the same way of testing. If there is none, the test waits for the repair. If the result will be late, sales tells the customer; the way of testing changes only when the customer agrees, through a revised quotation.

## Sampling and sample collection

- **Sampling requirements.** Each testing method states, per sample type, the amount of sample, the container type and the preservation condition it needs. Methods with the same container type and preservation condition share one physical sample, and their amounts add up. The container type is an attribute, not a managed item.
- **Expected number of samples.** Computed when the customer orders and shown to them, with the container and amount of each sample. For each sample type, the number of objects is the largest quantity among the order lines of that type; the number of samples is the number of objects times the number of sampling groups.
- **Customers do not declare samples.** The sample collection staff adjust the samples to what is actually collected, and the customer signs to confirm. This answers "Samples in a parameter-first order" in [E-commerce questions](ecommerce.md): the collection staff group the ordered tests into physical samples at collection, guided by the expected samples.
- **Sample collection is a record.** Each collection or hand-over records the staff member, the appointment and the collection time, the samples received, the differences from the order and the customer's confirmation signature. A test request can have several collections. Changes the SampleCollection glossary entry, which describes only a step.
- **Fewer samples than ordered.** Sales either waits for another collection or cancels the missing part; the final invoice reflects what was tested.
- **More samples than ordered.** Extra samples are received and held as pending. Sales issues a revised quotation, and the extra samples are tested only after the customer agrees.
- **Expected samples on the test request** (21-10-2026). Confirming the order creates the test request with its expected samples, in the `expected` state, worked out from the sampling requirements, each with the sample tests it carries. The sample collection staff adjust them to what is collected. A test request always has at least one sample, as the [Laboratory overview](../docs/functional/laboratory_module/overview.md) diagram says.
- **A sample test has its way of testing from the start.** `sample_test.parameter_method_id` becomes required, and `sample_test.parameter_id` only repeats the parameter of that way of testing.

## Scheduling and results

- **Scheduling is part of the system.** It plans test runs and sample collection appointments, and reads machine downtime from machine services. Staff shifts and leave come from the HR people source.
- **Test runs.** A test run is one run on one machine, by one person, in one time slot, measuring attempts of one way of testing. Machines are linked to the ways of testing they can run, and scheduling picks one of them. A machine booking holds the slot of a test run, not of one sample test.
- **Run capacity** (21-10-2026). The link between a machine and a way of testing gives the most attempts one run takes, such as 40 positions of an ICP-MS. A run takes attempts of several samples, customers and test requests, all of the same way of testing.
- **Results are attempts.** Each test result is one attempt, measured in exactly one test run or one subcontract dispatch. A retest is a new attempt in a new run. The run gives the machine, the person and the time.
- **Personnel authorization.** Each person is authorized for specific parameters, and only authorized people are scheduled for them. This answers "Staff competence" in [Laboratory questions](laboratory.md): authorization is per parameter, not per testing method (21-10-2026).
- **Subcontract dispatch.** Sending samples to a subcontractor is a record: the subcontractor, the sending date, the due date, the attempts sent and the subcontractor's report.
- **Testing figures** (21-10-2026). For a period, a head of department sees for their department, and the lab head for every department: the sample tests completed, the share completed on time, the average time from receipt to approval, the sample tests overdue, the retests and the workload of each person. This answers "Turnaround reporting" in [Laboratory questions](laboratory.md).

## Signing and changes

- **Change requests.** Change requests apply to test results, test reports, quotations and orders. Posted invoices are corrected with credit notes instead.
- **Who signs results and reports** (21-10-2026). The head of department approves test results and the lab head signs the test report; the proposal's "sign their test results" for the lab head means the report. The examples of SH-04 and SH-07 in [Shared technical features](../docs/functional/shared.md), "the Lab Head for a test result", change to the head of department for a test result and the lab head for a test report.

## Catalog

Decided on 21-10-2026 from the accreditation scope VILAS 677, compared with VILAS 252, 238 and 092.

- **Product groups are sample types.** The proposal's product group is a sample type with narrower types, not a level of its own, and the word "product" is not used for it. Changes [Laboratory administrator](../docs/functional/laboratory_module/features/admin.md) lines 13 and 54 and the SampleType entry of the [Glossaries](../docs/glossaries.md).
- **Sample type roots.** The roots of the sample type tree are food and the materials an accreditation scope names beside it: health supplements (TPBVSK), food additives, animal feed, water, cosmetics, food-contact packaging and veterinary drugs. The tree has no fixed depth. Changes only the demo data.
- **Accreditation follows scope lines.** A line of an accreditation certificate is a method with its parameters and sample types. A sample test is accredited when its in-house way of testing is on a line of a valid certificate and its sample's type is that line's type or a narrower one, so `is_accredited` moves from ParameterMethod to SampleTest. Changes [Laboratory administrator](../docs/functional/laboratory_module/features/admin.md) lines 59, 60 and 62 and its acceptance criteria, the ParameterMethod entry of the [Glossaries](../docs/glossaries.md), [laboratory.prisma](../docs/infrastructure/database/laboratory/laboratory.prisma) and the accreditation rules of [Business flows](../docs/functional/business-flows.md).
- **Method codes as the scope prints them.** A testing method's code is the standard as the scope prints it, without the parenthesis, with an optional reference or equivalent standard. On import, the title is optional and defaults to the code. A new edition of a standard is a new testing method; methods have no versions. Changes [Laboratory administrator](../docs/functional/laboratory_module/features/admin.md) lines 56 and 60 and [laboratory.prisma](../docs/infrastructure/database/laboratory/laboratory.prisma).
- **Testing fields use the VILAS names** Sinh, Hóa and Dược. Changes [Laboratory administrator](../docs/functional/laboratory_module/features/admin.md) line 56, the TestingField entry of the [Glossaries](../docs/glossaries.md) and the demo data.
- **Demo catalog from a real scope.** The demo catalog is replaced by 20 to 30 lines of the VILAS 677 scope across Sinh and Hóa, a three-level sample type tree and at least one sample test outside the scope. It keeps facts only, such as standard codes, analytes and LOQs: no PDF and no contact details.

## Commercial

- **Head of Sales approval before sending** (21-10-2026). A quotation whose discount or total exceeds a threshold the Head of Sales sets needs the Head of Sales's approval before sales sends it; below the thresholds, sales sends it alone. Changes [Sales](../docs/functional/ecommerce_module/features/sales.md), which has the Head of Sales approve only the confirmed order.
- **Discounts in percent only, for now** (21-10-2026). Sales discounts a line by a percentage, or the whole quotation by a discount line worked out from a percentage; fixed amounts are not offered. Changes the Prices rule of [Sales](../docs/functional/ecommerce_module/features/sales.md), which allows a fixed amount. See "Fixed-amount discounts" in [E-commerce questions](ecommerce.md).
- **Payments above the amount due** (21-10-2026). A new cash, bank transfer or PayOS amount above an invoice's remaining amount is refused. A PayOS transfer that has already arrived is recorded in full, and its excess is flagged for the accountant and not refunded, as the [payments spec](../docs/specs/payments.md) says. Changes the Partial payments rule of [Accountant](../docs/functional/ecommerce_module/features/accountant.md), which refuses any payment above the remaining amount.
- **What confirms a PayOS payment** (21-10-2026). PayOS's signed notification, or the status PayOS returns when the system asks for pending payments, confirms a payment; the customer's browser returning to the website never does. Changes the wording of the PayOS section of [Shared technical features](../docs/functional/shared.md) and of the Goal of the [PayOS spec](../docs/specs/payos.md), which name only the signed notification.
- **Customers request priority** (21-10-2026). A customer marks an order as priority on the portal; sales checks whether the laboratory can take it (US-S22) and accepts or declines the priority on the quotation. The surcharge stays open as "Priority surcharge" in [E-commerce questions](ecommerce.md).

## Platform

- **Internal messaging** (21-10-2026). Internal users chat in Odoo Discuss and discuss a record in its chatter, as Odoo provides them. Adds a requirement to [Shared technical features](../docs/functional/shared.md), which uses both without stating it.

## Scope of the conceptual model

- **Modules.** Laboratory, E-commerce, Inventory and scheduling. Medilab Sync is left out.
- **Left out as technical or attribute-level:** audit entries, notifications and email messages, notification preferences, the signing certificate, payment methods, portal accounts (part of Customer and Person), roles, document versions and signed PDFs.
- **Folded into another entity:** gateway transactions into Payment, tax rates into Tax, unit categories into MeasurementUnit, parameter prices into TestParameter and subcontract costs into ParameterMethod. Invoice lines are left out.
- **Drawn as many-to-many relationships:** regulation limits (Regulation–TestParameter), service package lines (ServicePackage–TestParameter) and chemical consumption (TestingMethod–Chemical).

## New glossary terms

To add to the [Glossaries](../docs/glossaries.md) when the documents are updated.

| Name (en)           | Name (vi)          | Description (en)                                                                                                   |
| ------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------ |
| SamplingRequirement | Yêu Cầu Lấy Mẫu    | The amount, container and preservation a testing method needs for a sample type.                                  |
| ContactPerson       | Người Liên Hệ      | A person of a business customer or of a subcontractor.                                                             |
| SampleTest          | Chỉ Tiêu Của Mẫu   | One way of testing applied to one sample.                                                                          |
| TestRun             | Mẻ Thử             | One run on one machine, by one person, in one time slot.                                                           |
| OrderLine           | Dòng Đơn Hàng      | One parameter, with its chosen or default way of testing, or one service package, in an order, with a sample type and a number of samples. |
| OrderTemplate       | Đơn Thường Dùng    | A saved order a customer reuses to order again; it has no price of its own. "Mẫu" is avoided because it means sample. |
| Payment             | Thanh Toán         | One payment, possibly partial, including gateway payments.                                                         |
| Feedback            | Đánh Giá           | A customer's rating and comment on a completed order.                                                              |
| InternalMovement    | Điều Chuyển Nội Bộ | One movement of a chemical inside the laboratory.                                                                  |
| Lab QA              | Thử Nghiệm Viên    | Another name for Tester in the documents. It does not mean quality assurance: QA and QC are roles of laboratories inside factories, and this laboratory has no QA or QC role. |

Existing entries whose meaning changes: TestResult (one attempt), SampleCollection (a record) and Regulation, which the old Odoo repository called "quy chuẩn so sánh" (comparison standard).

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
- [Laboratory administrator](../docs/functional/laboratory_module/features/admin.md)
- [E-commerce overview](../docs/functional/ecommerce_module/overview.md)
- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
- [Sales order and customer order](../docs/business/sales-order-and-customer-order.md)
- [Shared technical features](../docs/functional/shared.md)
- [Business flows](../docs/functional/business-flows.md)
- [Payments spec](../docs/specs/payments.md)
- [PayOS spec](../docs/specs/payos.md)
- [Glossaries](../docs/glossaries.md)
- [laboratory.prisma](../docs/infrastructure/database/laboratory/laboratory.prisma)
- [ecommerce.prisma](../docs/infrastructure/database/ecommerce/ecommerce.prisma)
- [Reports](../docs/reports/readme.md)
- [Laboratory questions](laboratory.md)
- [E-commerce questions](ecommerce.md)
