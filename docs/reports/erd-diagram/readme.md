# Conceptual ERD

The business concepts of the Laboratory and E-commerce modules and how they relate, drawn in Chen notation. The
[conceptual model](../../functional/conceptual-model.md), the [glossary](../../glossaries.md) and the actor features
are the sources; the tables of this document are the model: [erd_diagram.py](erd_diagram.py) reads them and draws one
overview and one diagram per area. The diagrams are drawn with PlantUML, not Mermaid, because Mermaid has no Chen
notation and cannot lay out 49 entities readably.

![Conceptual ERD overview](conceptual.svg)

## Files

- [conceptual.puml](conceptual.puml) and [conceptual.svg](conceptual.svg): the overview, with its entity positions in
  [overview-layout.json](overview-layout.json)
- [conceptual.drawio](conceptual.drawio): the overview for draw.io, written from conceptual.svg with the same
  positions; its lines stay attached to their shapes. Each `1` or `N` sits beside its line just outside the entity,
  clear of every shape, label and other line. It is regenerated with the diagrams, so edits made in draw.io are
  overwritten
- `conceptual-<area>.puml` and `conceptual-<area>.svg`: one diagram per area, listed in [Diagrams](#diagrams)
- [erd_diagram.py](erd_diagram.py): reads the tables of this document and writes the diagrams

After changing a table, regenerate the diagrams. The overview keeps the saved positions; `--relayout` searches new
positions when an entity is added or removed, which takes several minutes:

```bash
python docs/reports/erd-diagram/erd_diagram.py --plantuml <plantuml.jar>
uv run --no-project --with numpy --with networkx --with scipy python docs/reports/erd-diagram/erd_diagram.py --plantuml <plantuml.jar> --relayout
```

PlantUML 1.2026.6 or later and Graphviz are required. The script stops without writing when the tables are
inconsistent, and prints the line crossings of the rendered overview.

## Reading the diagrams

- A rectangle is an entity: its English glossary name on top, its Vietnamese name below. A diamond is a relationship,
  labelled with the verb of the conceptual model.
- `1` or `N` next to an entity is the largest number of that entity in the relationship, seen from one entity on the
  other side. `N` on both sides is many-to-many.
- A bold line means total participation: every entity on that side takes part in the relationship. A thin line means it
  may not.
- In the overview, the fill colour gives the area. Signature and ChangeRequest are repeated as grey dashed copies next
  to the areas that use them, so their lines stay short; a copy is the same entity.
- In an area diagram, a grey entity belongs to another area and is drawn only for its relationships with this one.

## Scope

- The Laboratory and E-commerce modules. Inventory, Onboarding and Medilab Sync are not drawn.
- Business concepts only, without attributes. Technical concepts, portal accounts, roles, document versions and
  signed PDFs are omitted, as in the [conceptual model](../../functional/conceptual-model.md#model-scope).

## Method

A data model holds many tables that are not business concepts. Each candidate goes through these steps in order and
stops at the first that applies:

| Step | Test | Result |
| --- | --- | --- |
| 1 | Infrastructure or technical: audit, notification, lock, job, file storage, login account, role and permission, signing certificate | Not drawn |
| 2 | Only how Odoo implements a concept that is already drawn | Not drawn; the concept is drawn |
| 3 | A computed value, a view or a statistic | Not drawn |
| 4 | Links two or three things and describes only that combination | Relationship, with its details as relationship attributes |
| 5 | One-to-one with another concept, without relationships or a life of its own | Attribute of that concept |
| 6 | A line of another concept | Entity when it has relationships or rules of its own; otherwise an attribute |
| 7 | Has its own identity and life cycle, a glossary entry, and an actor who creates, approves or uses it | Entity |

[Not drawn](#not-drawn) lists the candidates that stop before step 7.

## Diagrams

The numbers in brackets are rows of [Relationships](#relationships).

### Overview

[conceptual.svg](conceptual.svg): all 49 entities and 82 relationships, with 4 copies of Signature and 4 of
ChangeRequest. Measured on the SVG, 20 pairs of lines cross and no line passes through a box. ParameterMethod,
SampleType, Sample, SaleOrder and Person are the most connected entities.

### Catalog

[conceptual-catalog.svg](conceptual-catalog.svg)

- A ParameterMethod is one parameter, one method and one performing party: a department (5) or a subcontractor (6).
- The explicit applicability (7) carries the unit, LOD and LOQ, precision and default way per parameter and sample
  type. The sampling requirement (8) and the regulation limit (15) are relationships; see [Findings](#findings).
- QualityRegistration (79) and TestingField (80) are not in the conceptual model. The Vietnamese name of
  AccreditationScopeLine is provisional.
- Tax applies to the prices of TestParameter and ServicePackage (74, 75), drawn in Finance.

### Resources

[conceptual-resources.svg](conceptual-resources.svg)

- A Person is drawn only where a person decides a rule: their department (28), parameter authorization (29), bookings
  (31), collections (42), planned overtime (41), signatures (60) and the orders they are salesperson of (82). Who
  recorded, cancelled or handled a record is an attribute.
- A ContactPerson belongs to a customer or to a subcontractor, never to both (43, 44).
- A Location is reached only through bookings (34); method steps and shared room bookings are not drawn; see
  [Deviations from the proposal](#deviations-from-the-proposal).

### Scheduling

[conceptual-scheduling.svg](conceptual-scheduling.svg)

- A TestResult belongs to exactly one MachineBooking (35) or one SubcontractDispatch (38), never both. Chen notation
  cannot draw "exactly one of the two", so both lines are thin.
- A PlanRevision moves at least one booking and needs the head of each affected department (36, 37).
- A SubcontractDispatch carries results (38), not sample tests.

### Testing

[conceptual-testing.svg](conceptual-testing.svg)

- A TestRequest comes only from a SaleOrder (54) and includes at least one sample from confirmation (17).
- A sample can be in several collections (19) and is handed over to each department that tests it (81).
- TestResult and TestReport are signed and changed through the approval entities (61, 62, 65, 66); the TestReport is
  what is released and delivered.

### Approval

[conceptual-approval.svg](conceptual-approval.svg)

- A Signature belongs to one document of one type: a TestResult, TestReport, Quotation or ChangeRequest (61 to 64). A
  ChangeRequest targets a TestResult, TestReport, Quotation or SaleOrder (65 to 68). Those lines are thin on the
  Signature and ChangeRequest side because the document can be of any of these types.
- Invoices are not signed here until the signed-invoices finding is decided.
- A result's change request triggers the change request of its issued report (69).

### Sales

[conceptual-sales.svg](conceptual-sales.svg)

- An OrderLine is one parameter or one whole package (51) for one sample type (47). Its OrderLineSelections keep one
  parameter and its way for each parameter it includes (48 to 50).
- A SaleOrder has several Quotations (53), creates at most one TestRequest (54) and has a salesperson (82).
- CancellationRequest and SupportRequest are not in the conceptual model. What an OrderTemplate holds is not drawn.

### Finance

[conceptual-finance.svg](conceptual-finance.svg)

- An Invoice belongs to one SaleOrder (70). An advance invoice comes from at most one Quotation (71). An
  AdjustmentInvoice corrects one Invoice (72).
- A Payment pays one Invoice (73); its receipt and its gateway transaction are attributes.
- Tax applies to parameter and package prices (74, 75); the tax copied onto order lines and invoices is not drawn.

## Entities

| Entity | Vietnamese | Area | Step | Source |
| --- | --- | --- | --- | --- |
| TestParameter | Chỉ Tiêu | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ParameterGroup | Nhóm Chỉ Tiêu | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleType | Loại Mẫu | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ParameterMethod | Cách Thử | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestingMethod | Phương Pháp Thử | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestingField | Lĩnh Vực Thử Nghiệm | Catalog | 7 | [Glossary](../../glossaries.md) |
| Chemical | Hóa Chất | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| MeasurementUnit | Đơn Vị Đo | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Regulation | Quy Chuẩn | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| AccreditationCertificate | Giấy Chứng Nhận Công Nhận | Catalog | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| AccreditationScopeLine | Dòng Phạm Vi Công Nhận | Catalog | 6 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); not in the glossary yet |
| QualityRegistration | Hồ Sơ Đăng Ký Chất Lượng | Catalog | 7 | [Glossary](../../glossaries.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| Department | Phòng Ban | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Person | Nhân Sự | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Machine | Máy | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| MachineService | Lịch Sử Bảo Trì Máy | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Location | Vị Trí | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Subcontractor | Thầu Phụ | Resources | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| MachineBooking | Lịch Đặt Máy | Scheduling | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| PlanRevision | Phương Án Xếp Lại Lịch | Scheduling | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| OverTime | Làm Thêm Giờ | Scheduling | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| SubcontractDispatch | Phiếu Gửi Thầu Phụ | Scheduling | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| TestRequest | Yêu Cầu Thử Nghiệm | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleCollection | Giao Nhận Mẫu | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| Sample | Mẫu | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleTest | Chỉ Tiêu Của Mẫu | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestResult | Kết Quả Thử Nghiệm | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleReturn | Trả Mẫu | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestReport | Phiếu Kết Quả | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ReportTemplate | Mẫu Phiếu Kết Quả | Testing | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ApprovalChain | Chuỗi Phê Duyệt | Approval | 7 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| ApprovalLevel | Cấp Phê Duyệt | Approval | 6 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| Signature | Chữ Ký | Approval | 7 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| ChangeRequest | Yêu Cầu Thay Đổi | Approval | 7 | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| Customer | Khách Hàng | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| ContactPerson | Người Liên Hệ | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| SaleOrder | Đơn Hàng | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderLine | Dòng Đơn Hàng | Sales | 6 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderLineSelection | Lựa Chọn Cách Thử Trên Dòng Đơn | Sales | 6 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Quotation | Báo Giá | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| ServicePackage | Nhóm Dịch Vụ | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderTemplate | Đơn Thường Dùng | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| CancellationRequest | Yêu Cầu Hủy | Sales | 7 | [Glossary](../../glossaries.md), [Sales](../../functional/ecommerce_module/features/sales.md) |
| SupportRequest | Yêu Cầu Hỗ Trợ | Sales | 7 | [Glossary](../../glossaries.md), [Sales](../../functional/ecommerce_module/features/sales.md) |
| Feedback | Đánh Giá | Sales | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Invoice | Hóa Đơn | Finance | 7 | [Glossary](../../glossaries.md), [Invoices](../../specs/invoices.md) |
| AdjustmentInvoice | Hóa Đơn Điều Chỉnh | Finance | 7 | [Glossary](../../glossaries.md), [Invoices](../../specs/invoices.md) |
| Payment | Thanh Toán | Finance | 7 | [Payments](../../specs/payments.md); not in the glossary yet |
| Tax | Thuế | Finance | 7 | [Glossary](../../glossaries.md) |

## Relationships

`Card 1` is the number of `End 1` entities for one entity at the other end, `Card 2` the number of `End 2` entities for
one `End 1` entity: `1`, `0..1`, `0..*` or `1..*`. A relationship of three entities lists its second and third ends
and their numbers joined by `+`.

| # | End 1 | Card 1 | Relationship | Card 2 | End 2 | Source |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | SampleType | 0..1 | broadens | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 2 | TestParameter | 0..* | belongs to | 0..* | ParameterGroup | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 3 | TestParameter | 1 | has | 0..* | ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 4 | ParameterMethod | 0..* | uses | 1 | TestingMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 5 | ParameterMethod | 0..* | performed in-house by | 0..1 | Department | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 6 | ParameterMethod | 0..* | performed externally by | 0..1 | Subcontractor | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 7 | ParameterMethod | 0..* | explicitly applies to | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); the sample-type applicability |
| 8 | TestingMethod | 0..* | needs sampling of | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); the sampling requirement |
| 9 | TestingMethod | 0..* | consumes | 0..* | Chemical | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 10 | AccreditationCertificate | 1 | contains | 1..* | AccreditationScopeLine | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 11 | AccreditationScopeLine | 0..* | covers | 1 | TestingMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 12 | AccreditationScopeLine | 0..* | covers | 1..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 13 | AccreditationScopeLine | 0..* | covers | 1..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 14 | Regulation | 0..* | applies to | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 15 | Regulation | 0..* | limits | 0..* + 0..* | TestParameter + SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); the regulation limit, unique per regulation, parameter and sample type |
| 16 | Customer | 1 | requests | 0..* | TestRequest | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 17 | TestRequest | 1 | includes | 1..* | Sample | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); confirming an order creates at least one expected sample |
| 18 | TestRequest | 1 | receives through | 0..* | SampleCollection | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 19 | SampleCollection | 0..* | records actual handover of | 0..* | Sample | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 20 | Sample | 0..* | has type | 1 | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 21 | Sample | 0..* | optionally compares against | 0..1 | Regulation | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 22 | Sample | 1 | carries | 1..* | SampleTest | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 23 | SampleTest | 0..* | uses from creation | 1 | ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 24 | SampleTest | 1 | has results | 0..* | TestResult | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 25 | Sample | 1 | is returned through | 0..* | SampleReturn | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 26 | TestRequest | 1 | reports | 0..* | TestReport | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 27 | ReportTemplate | 1 | prepares | 0..* | TestReport | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 28 | Department | 1 | contains | 0..* | Person | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 29 | Person | 0..* | authorized by lab head for | 0..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 30 | SampleTest | 1 | is booked in | 0..* | MachineBooking | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 31 | MachineBooking | 0..* | performed by | 1 | Person | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 32 | MachineBooking | 0..* | uses if required | 0..1 | Machine | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 33 | Machine | 0..* | has duration and capacity for | 0..* | TestingMethod | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 34 | MachineBooking | 0..* | reserves step intervals | 0..* | Location | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 35 | MachineBooking | 0..1 | measures | 0..* | TestResult | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 36 | PlanRevision | 0..* | moves | 1..* | MachineBooking | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 37 | PlanRevision | 0..* | approved by head of | 1..* | Department | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 38 | SubcontractDispatch | 0..1 | carries | 0..* | TestResult | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 39 | SubcontractDispatch | 0..* | sends to | 1 | Subcontractor | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 40 | Machine | 1 | has | 0..* | MachineService | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 41 | Person | 1 | has planned | 0..* | OverTime | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 42 | SampleCollection | 0..* | collected by | 1 | Person | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 43 | Customer | 0..1 | has | 0..* | ContactPerson | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory); a contact belongs to a customer or a subcontractor |
| 44 | Subcontractor | 0..1 | has | 0..* | ContactPerson | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory); a contact belongs to a customer or a subcontractor |
| 45 | Customer | 1 | places | 0..* | SaleOrder | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 46 | SaleOrder | 1 | selects | 1..* | OrderLine | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 47 | OrderLine | 0..* | for | 1 | SampleType | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 48 | OrderLine | 1 | retains | 1..* | OrderLineSelection | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 49 | OrderLineSelection | 0..* | for | 1 | TestParameter | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 50 | OrderLineSelection | 0..* | chooses | 1 | ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 51 | OrderLine | 0..* | buys whole | 0..1 | ServicePackage | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 52 | ServicePackage | 0..* | contains | 0..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 53 | SaleOrder | 1 | offers | 0..* | Quotation | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 54 | SaleOrder | 1 | creates | 0..1 | TestRequest | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 55 | Customer | 1 | reuses | 0..* | OrderTemplate | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 56 | SaleOrder | 1 | receives | 0..1 | Feedback | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 57 | Chemical | 0..* | measured in | 1 | MeasurementUnit | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 58 | ApprovalChain | 1 | contains | 1..* | ApprovalLevel | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| 59 | ApprovalLevel | 1 | records | 0..* | Signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| 60 | Person | 1 | signs | 0..* | Signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| 61 | TestResult | 0..1 | is signed through | 0..* | Signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing); a signature belongs to one document of one type |
| 62 | TestReport | 0..1 | is signed through | 0..* | Signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| 63 | Quotation | 0..1 | is signed through | 0..* | Signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing); above the approval thresholds |
| 64 | ChangeRequest | 0..1 | is signed through | 0..* | Signature | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| 65 | TestResult | 0..1 | is changed through | 0..* | ChangeRequest | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked); a change request targets one document of one type |
| 66 | TestReport | 0..1 | is changed through | 0..* | ChangeRequest | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| 67 | Quotation | 0..1 | is changed through | 0..* | ChangeRequest | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| 68 | SaleOrder | 0..1 | is changed through | 0..* | ChangeRequest | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| 69 | ChangeRequest | 0..1 | triggers | 0..* | ChangeRequest | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people); a result correction links the change request of its issued report |
| 70 | SaleOrder | 1 | is billed by | 0..* | Invoice | [Invoices](../../specs/invoices.md) |
| 71 | Quotation | 0..1 | has advance | 0..1 | Invoice | [Invoices](../../specs/invoices.md) |
| 72 | Invoice | 1 | is corrected by | 0..* | AdjustmentInvoice | [Glossary](../../glossaries.md) |
| 73 | Invoice | 1 | is paid by | 0..* | Payment | [Payments](../../specs/payments.md); a confirmed payment has one receipt |
| 74 | Tax | 1 | applies to | 0..* | TestParameter | [Glossary](../../glossaries.md); one tax per parameter price |
| 75 | Tax | 1 | applies to | 0..* | ServicePackage | [Glossary](../../glossaries.md); one tax per package |
| 76 | SaleOrder | 1 | has | 0..* | CancellationRequest | [Glossary](../../glossaries.md); at most one open request per order |
| 77 | Customer | 1 | opens | 0..* | SupportRequest | [Glossary](../../glossaries.md) |
| 78 | SaleOrder | 0..1 | is about | 0..* | SupportRequest | [Glossary](../../glossaries.md) |
| 79 | QualityRegistration | 0..* | covers | 0..* | ParameterMethod | [Glossary](../../glossaries.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| 80 | TestingField | 1 | classifies | 0..* | TestingMethod | [Glossary](../../glossaries.md) |
| 81 | Sample | 0..* | is handed over to | 0..* | Department | [Glossary](../../glossaries.md); the sample handover, one per sample and department |
| 82 | Person | 0..1 | is salesperson of | 0..* | SaleOrder | [Sales](../../functional/ecommerce_module/features/sales.md); decides the order's tasks and visibility |

## Not drawn

| Candidate | Step | Why |
| --- | --- | --- |
| AuditEntry, AuditChange, notifications and messages, DocumentLock, ScheduledJob, JobItem, JobRun, ArchiveFile, MobileDevice, PushDelivery | 1 | Technical |
| User, Role, RoleGrant, Permission, SigningCertificate, DigitalSignature | 1 | Login accounts, roles and certificates |
| Product, Combo, Contact, Employee, CalendarEvent, Attachment | 2 | Odoo records behind TestParameter, ServicePackage, Customer, ContactPerson, Subcontractor and Person |
| OrderSample, SchedulingPlan, Queue, MachineSchedule, PersonalSchedule, OutsourcingSuggestion, OutsourcingSchedule, ToDoList, Revenue, Outstanding, CashFlow, CollectionPerformance, SalesPipeline, SalesPerformance | 3 | Computed or a view |
| SamplingRequirement, RegulationLimit, ParameterMethodSampleType, SampleHandover | 4 | Relationships 8, 15, 7 and 81 |
| Receipt, PendingPayment, TaxRate, ParameterPrice, SubcontractCost, CustomerSalesTerms, NotificationContact, SampleLabel, LabCode | 5 | Attributes of Payment, Tax, TestParameter, ParameterMethod, Customer and ContactPerson |
| SigningProcess | 5 | The chain levels one document version keeps; document versions are out of scope |
| InvoiceLine, OrderTemplateLine, TestingMethodStep | 6 | Lines without relationships drawn here |
| HandoverRecord | 7 | The same concept as SampleCollection |
| Task, TaskType | 7 | The work queue of [SH-10](../../functional/shared.md#sh-10-tasks-and-to-do-list), not a business record |
| PaymentTransaction, ReconciliationDay | 7 | Payment gateway records, part of Payment |
| Team, stock, recipes, purchasing, laboratory files, onboarding | Scope | Inventory, Medilab Sync and Onboarding |

## Findings

Points where the [conceptual model](../../functional/conceptual-model.md) or the [glossary](../../glossaries.md)
disagree with the other documents. The ERD follows the column "ERD"; the documents are not changed yet.

| Topic | What the documents say | ERD |
| --- | --- | --- |
| Signing and change requests | The conceptual model draws neither, although [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) signs test results, test reports, quotations above the thresholds and change requests, and [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) changes results, reports, quotations and orders through change requests | ApprovalChain, ApprovalLevel, Signature and ChangeRequest, relationships 58 to 69 |
| Invoices and payments | The conceptual model leaves them to the E-commerce specifications; the glossary defines them and the Accountant works with them | Invoice, AdjustmentInvoice, Payment and Tax, relationships 70 to 75 |
| Other concepts of the glossary | QualityRegistration, TestingField, CancellationRequest, SupportRequest and the sample handover to departments are not in the conceptual model | Drawn, relationships 76 to 81 |
| Sampling requirement and regulation limit | The conceptual model draws them as entities, but each describes one combination: a method and a sample type, and a regulation, a parameter and a sample type | Relationships 8 and 15 |
| Contact persons | The conceptual model makes every contact person belong to exactly one customer and to exactly one subcontractor at the same time | A contact person belongs to a customer or to a subcontractor, relationships 43 and 44 |
| Linked change requests | The text of the conceptual model links a result correction to the change request of the issued report, its diagram does not | Relationship 69 |
| Signed invoices | The Documents row of [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) lists invoices, but [Invoices](../../specs/invoices.md) and the [Accountant](../../functional/ecommerce_module/features/accountant.md) define no approval chain for them | Not drawn until decided |
| SampleCollection and HandoverRecord | The glossary has both for the samples a customer hands over and signs for | SampleCollection only |
| Payment | The glossary has no Payment entry, although PendingPayment and Receipt are defined through payments | Payment, with a provisional Vietnamese name |
| QualityRegistration | The glossary covers the ways of testing of "a parameter"; the [Laboratory administrator](../../functional/laboratory_module/features/admin.md) covers "each covered parameter" | Many-to-many with ParameterMethod, relationship 79 |
| AccreditationScopeLine | No glossary entry | A provisional Vietnamese name |
| Order template contents | The conceptual model does not say what a template holds | Not drawn |

## Deviations from the proposal

Quotes are from the [capstone proposal](../proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx),
with their section; each is one sentence that can be searched for.

**Proposal concepts the ERD leaves out**

| Topic | Proposal | ERD | Documents |
| --- | --- | --- | --- |
| Method steps | *c) Functional Requirements → 1. Administrator → Master Data & Service Catalog*: "Manage testing method steps, accreditation certificates, and chemicals." | Steps are attributes of TestingMethod; where a step is done is not drawn | [Laboratory overview](../../functional/laboratory_module/overview.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| Laboratory files | *c) Functional Requirements → 5. Tester (Lab QA) → Laboratory File Management*: "Synchronize and maintain versioned laboratory files, including synchronization and conflict status." | Left out with Medilab Sync, although folders, files and versions are Laboratory models and a Signature can sign a file version | [Laboratory overview](../../functional/laboratory_module/overview.md), [Module boundaries](../../business/module-boundaries.md) |
| Tasks | *c) Functional Requirements → 6. Department Head → Department & Task Management*: "Reassign testing tasks." | The work queue of SH-10 is not drawn; a testing task stands for one SampleTest and a collection task for one SampleCollection | [SH-10](../../functional/shared.md#sh-10-tasks-and-to-do-list) |
| Shared room bookings | *c) Functional Requirements → 5. Tester (Lab QA) → Testing Task Management*: "Book shared testing rooms." | Only a booking of a sample test reserves a Location; a booking of a room alone is a calendar event | [SH-11](../../functional/shared.md#sh-11-schedules-and-reminders) |
| Audit trail | *d) Non-Functional Requirements → Security*: "Maintain audit trails for critical data changes, approvals and digital signatures." | Technical, not drawn | [SH-05](../../functional/shared.md#sh-05-audit-trail) |
| Notifications and messaging | *c) Functional Requirements → 10. Authorized Internal Users → Communication & Notifications*: "Receive status, rejection, deadline, and assigned-task notifications." | Technical, not drawn | [SH-11](../../functional/shared.md#sh-11-schedules-and-reminders), [SH-12](../../functional/shared.md#sh-12-conversations) |
| Roles and permissions | *c) Functional Requirements → 1. Administrator → User, Role & Access Management*: "Manage users, roles, permissions, and role-/field-level access control." | Not drawn; the role an ApprovalLevel names is an attribute | [Glossaries](../../glossaries.md) |
| Daily reconciliation | *c) Functional Requirements → 3. Finance → Payment Management*: "Confirm payments recorded by sales and reconcile daily online payments." | The reconciliation day is not drawn | [Accountant](../../functional/ecommerce_module/features/accountant.md) |
| Product groups and catalog tree | *c) Functional Requirements → 1. Administrator → Master Data & Service Catalog*: "Manage laboratory catalog tree (product group, parameter group, parameter, method)" | No product group, which no document names; the nearest is a broad SampleType. The catalog is a set of links, not one tree | [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| Portal accounts | *c) Functional Requirements → 9. Customer → Portal & Account Access*: "Access the customer portal, manage basic profile information, and view submitted test requests and their status." | Part of Customer, ContactPerson and Person | [Conceptual model](../../functional/conceptual-model.md#model-scope) |
| Signing identities | *c) Functional Requirements → 1. Administrator → System Configuration*: "Manage digital-signature identities and integrations." | One laboratory certificate signs every digitally signed document and is not drawn; Signature keeps the signing history | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| Document versions | *d) Non-Functional Requirements → Reliability & Data Integrity*: "Preserve traceability of samples, test results, approvals and document versions." | No version entity: the versions of a quotation are Quotations of one SaleOrder, those of results and reports come through ChangeRequest | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| Staff absence | *c) Functional Requirements → 6. Department Head → Scheduling & Prioritization*: "Reschedule bookings when staff are absent or machines are unavailable." | Shifts and leave come from HR and are not drawn; machine downtime is MachineService | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |

**Proposal concepts the ERD models or names differently**

| Topic | Proposal | ERD | Documents |
| --- | --- | --- | --- |
| Test requests and orders | *c) Functional Requirements → 9. Customer → Test Request & Quotation*: "Submit testing requests and select required laboratory services." | The customer submits a SaleOrder; the TestRequest is created when Sales confirms it | [E-commerce overview](../../functional/ecommerce_module/overview.md) |
| Test requests at reception | *c) Functional Requirements → 4. Sampling and Reception → Sample Reception*: "Create test requests at reception." | A TestRequest comes only from a confirmed SaleOrder | [Sample Delivery Staff](../../functional/laboratory_module/features/sample-delivery-staff.md) |
| Test results and test reports | *c) Functional Requirements → 7. Lab Head → Test Result Release*: "Release test results only after required approvals and signatures and maintain released test result records." | What is released, signed and delivered is the TestReport | [Lab Head](../../functional/laboratory_module/features/lab-head.md) |
| Tester signature | *c) Functional Requirements → 5. Tester (Lab QA) → Testing & Result Entry*: "Submit completed results for review and apply the tester-level digital signature." | A Signature at a level of the result's approval chain, not a digital signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| Head of department signature | *c) Functional Requirements → 6. Department Head → Result Review & Approval*: "Review tester results and either approve them with a digital signature or reject/return them for revision." | A Signature or rejection at the result's approval level, not a digital signature | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| Retained samples | *c) Functional Requirements → 4. Sampling and Reception → Sample Retention*: "Register retained samples, track retention periods, and record disposal after expiry." | Retention is attributes of SampleType and states of Sample; SampleReturn records a return | [Laboratory overview](../../functional/laboratory_module/overview.md) |
| Handover between departments | *c) Functional Requirements → 4. Sampling and Reception → Sample Coding & Routing*: "Confirm sample handover between departments by QR scanning." | Relationship 81 of Sample and Department, with no transfer from one department to another | [Laboratory overview](../../functional/laboratory_module/overview.md) |
| Discounts | *c) Functional Requirements → 2. Sales → Quotation & Order Management*: "Apply quotation discounts." | An attribute of OrderLine or Quotation | [Sales](../../functional/ecommerce_module/features/sales.md) |
| Quotation templates | *c) Functional Requirements → 2. Sales → Quotation & Order Management*: "Manage quotation templates." | OrderTemplate, a customer's saved order without prices | [Sales](../../functional/ecommerce_module/features/sales.md) |
| Receipts | *c) Functional Requirements → 9. Customer → Payment*: "Download receipt and invoice." | An attribute of Payment | [Payments](../../specs/payments.md) |
| Technical and reference standards | *c) Functional Requirements → 1. Administrator → Master Data & Service Catalog*: "Manage technical standards, regulations, specification limits, and reference-standard information." | A standard is the code of a TestingMethod; specification limits are relationship 15 | [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| Testing rooms | *b) Proposed Solutions*: "Machine & Testing Room Management" | Location | [Glossaries](../../glossaries.md) |
| Service and subcontractor prices | *c) Functional Requirements → 1. Administrator → System Configuration*: "Manage taxes, service packages, and subcontractor prices." | Prices are attributes of TestParameter, ServicePackage and ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#model-scope) |
| Partner information | *c) Functional Requirements → 1. Administrator → System Configuration*: "Manage customer, subcontractor, and partner information." | Customer, Subcontractor and ContactPerson | [Module boundaries](../../business/module-boundaries.md) |

**ERD concepts the proposal does not have**

| Topic | ERD | Documents |
| --- | --- | --- |
| Sample returns | SampleReturn | [Sample Delivery Staff](../../functional/laboratory_module/features/sample-delivery-staff.md) |
| Support requests | SupportRequest | [Customer](../../functional/ecommerce_module/features/customer.md) |
| Feedback | Feedback | [Customer](../../functional/ecommerce_module/features/customer.md) |
| Planned overtime | OverTime | [Head of Department](../../functional/laboratory_module/features/head-of-department.md) |
| Quality registrations | QualityRegistration | [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |

## Related documents

- [Conceptual model](../../functional/conceptual-model.md)
- [Glossaries](../../glossaries.md)
- [Use case diagram](../use-case-diagram/readme.md)
- [Context diagram](../context-diagram/readme.md)
- [Capstone proposal](../proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx)
- [Reports](../readme.md)
