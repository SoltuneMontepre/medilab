# Conceptual ERD

The business concepts of the Laboratory and E-commerce modules and how they relate, drawn in Chen notation. The
[conceptual model](../../functional/conceptual-model.md), the [glossary](../../glossaries.md) and the actor features
are the sources; the tables of this document are the model: [erd_diagram.py](erd_diagram.py) reads them and draws one
overview and one diagram per area. The diagrams are drawn with PlantUML, not Mermaid, because Mermaid has no Chen
notation and cannot lay out 53 entities readably.

![Conceptual ERD overview](conceptual.svg)

## Files

- [conceptual.puml](conceptual.puml): the overview for Graphviz, with its entity positions in
  [overview-layout.json](overview-layout.json)
- [conceptual.drawio](conceptual.drawio): the overview for draw.io, converted from the Graphviz rendering with the same
  positions; its lines stay attached to their shapes. Each `1` or `M` sits beside its line just outside the entity,
  clear of every shape, label and other line, and nearer its own line than any other. It is regenerated with the
  diagrams, so edits made in draw.io are overwritten
- [conceptual.svg](conceptual.svg): the overview exported from conceptual.drawio by draw.io
- `conceptual-<area>.puml` and `conceptual-<area>.svg`: one diagram per area, listed in [Diagrams](#diagrams).
  PlantUML has no composite entity and draws one label per line, so the script adds the diamond of each composite
  and both labels of its lines to the SVG
- [erd_diagram.py](erd_diagram.py): reads the tables of this document and writes the diagrams

After changing a table, regenerate the diagrams. The overview keeps the saved positions; `--relayout` searches new
positions when an entity is added or removed, which takes several minutes:

```bash
python docs/reports/erd-diagram/erd_diagram.py --plantuml <plantuml.jar> --drawio <draw.io executable>
uv run --no-project --with numpy --with networkx --with scipy python docs/reports/erd-diagram/erd_diagram.py --plantuml <plantuml.jar> --drawio <draw.io executable> --relayout
```

PlantUML 1.2026.6 or later, Graphviz and draw.io desktop are required; on Windows the draw.io executable is
`C:\Program Files\draw.io\draw.io.exe`. The script stops without writing when the tables are inconsistent, and prints
the line crossings of the Graphviz rendering of the overview.

## Reading the diagrams

The symbols are those of the Chen column of the course slides *Chapter 4. High-Level Database Model*, which write
many as `M`.

- A rectangle is an entity: its English glossary name on top, its Vietnamese name below. A diamond is a relationship,
  labelled with the verb of the conceptual model.
- A double rectangle is a weak entity, identified only within the entity it belongs to. A double diamond is its
  supporting relationship with that entity.
- A diamond inside a rectangle is a composite entity, also called an associative entity: one for each combination of
  the entities it links, drawn as an entity because the documents name it. Its box has the size of any entity, and its
  diamond is faint so the name written over it stays readable. Each of its lines is one-to-many: `1` beside the entity
  it links, `M` beside the composite.
- `1` or `M` next to an entity is the largest number of that entity in the relationship, seen from one entity on the
  other side. `M` on both sides is many-to-many. The smallest number, whether an entity must take part, is not drawn;
  [Relationships](#relationships) gives it.
- In the overview, the fill colour gives the area. Signature and ChangeRequest are repeated as grey dashed copies next
  to the areas that use them, so their lines stay short; a copy is the same entity.
- In an area diagram, a grey entity belongs to another area and is drawn only for its relationships with this one.

## Scope

- The Laboratory and E-commerce modules. Inventory, Onboarding and Medilab Sync are not drawn. Chemical, master data
  of the Laboratory module, is not drawn either, as the PO decided: see [Not drawn](#not-drawn).
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
| 4 | Links two or three things and describes only that combination | Composite entity when the glossary or the conceptual model names it; otherwise a relationship, with its details as relationship attributes |
| 5 | One-to-one with another concept, without relationships or a life of its own | Attribute of that concept |
| 6 | A line or a part of another concept | Weak entity of that concept when it has relationships or rules of its own; otherwise an attribute |
| 7 | Has its own identity and life cycle, a glossary entry, and an actor who creates, approves or uses it | Entity |

[Not drawn](#not-drawn) lists the candidates that stop before step 7.

Each entity then has one of three kinds. The weak entity follows the definition of slides 13 and 14 of the same
course; the slides show only the symbol of the composite entity (slide 9), so its test below is this ERD's. `Identified
by` in [Entities](#entities) names the entity a weak entity belongs to, or the entities a composite entity links.

| Kind | Test | Drawn as |
| --- | --- | --- |
| Weak | Its key includes the key of the one entity it belongs to, plus a number or a choice of its own (slide 13). The supporting relationship gives each weak entity exactly one such entity (slide 14) | Double rectangle; the supporting relationship is a double diamond |
| Composite | Identified by the two or three entities it links: one of it for each combination of them | Diamond inside a rectangle, the symbol of slide 9, joined to each entity it links by a one-to-many line |
| Strong | Neither: it has a code or a record of its own | Rectangle |

## Diagrams

The numbers in brackets are rows of [Relationships](#relationships).

### Overview

[conceptual.svg](conceptual.svg): all 53 entities and 88 relationships, with 4 copies of Signature and 4 of
ChangeRequest. Measured on the Graphviz rendering, 36 pairs of lines cross and no line passes through a box; every
`1` and `M` is clear of shapes, labels and other lines. The line from MeasurementUnit to its diamond (90) touches the
tip of the diamond of relationship 33. SaleOrder, SampleType, TestParameter and Sample are the most
connected entities.

### Catalog

[conceptual-catalog.svg](conceptual-catalog.svg)

- A ParameterMethod is a composite of one parameter and one method (3), and every parameter has at least one. It has
  one performing party: a department (5) or a subcontractor (6). Chen notation cannot draw a link to one of two
  entities, so the party stays outside the composite.
- The explicit applicability (7) carries the unit, LOD and LOQ, precision and default way per parameter and sample
  type; the glossary has no entry for it, so it stays a relationship. The SamplingRequirement (8) and the
  RegulationLimit (15) are composite entities: one per method and sample type, and one per regulation, parameter and
  sample type.
- A TestParameter belongs to groups (2) and is reported under one of them, the group revenue reports count it under
  (88). A ParameterGroup can be a sub-group of another (89).
- A TestingMethodStep is numbered within its method (4) and can name the Location where it is done (83). An
  AccreditationScopeLine is a line of its certificate (10).
- QualityRegistration (79) and TestingField (80) are not in the conceptual model.
- MeasurementUnit is linked only to SampleType, as the unit of the smallest amount of sample to collect (90). The
  result unit of a way on a sample type is an attribute of relationship 7, and a TestResult keeps a copy of it, so
  neither is drawn.
- In conceptual-catalog.svg PlantUML draws three lines into the same point of SampleType, on top of each other for a
  stretch; the `1` of the SamplingRequirement line sits beside that bundle.
- Tax applies to the prices of TestParameter and ServicePackage (74, 75), drawn in Finance.

### Resources

[conceptual-resources.svg](conceptual-resources.svg)

- A Person is drawn only where a person decides a rule: their department (28), parameter authorization (29), bookings
  (31), collections (42), planned overtime (41), signatures (60) and the orders they are salesperson of (82). Who
  recorded, cancelled or handled a record is an attribute.
- A ContactPerson belongs to a customer or to a subcontractor, never to both. It is not weak: it has no single entity
  it always belongs to (43, 44).
- A Location can be inside another (84). A method step is done in one (83), a sample is taken from one (23) and a
  booking reserves them (34). Shared room bookings are not drawn; see
  [Deviations from the proposal](#deviations-from-the-proposal).

### Scheduling

[conceptual-scheduling.svg](conceptual-scheduling.svg)

- A TestResult measured in the laboratory belongs to exactly one MachineBooking (35). An outsourced one has no booking
  and belongs to its SampleTest (24), which a SubcontractDispatch sends to the subcontractor (38). Chen notation cannot
  draw that a result has a booking only when measured in the laboratory.
- A PlanRevision moves at least one booking and needs the head of each affected department (36, 37).
- A SubcontractDispatch sends at least one SampleTest (38); a sample test can be in several dispatches, such as after a
  cancelled one.

### Testing

[conceptual-testing.svg](conceptual-testing.svg)

- A TestRequest comes only from a SaleOrder (54) and includes at least one sample from confirmation (17).
- A SampleTest is a composite of one sample and one way, required from creation (22). A TestResult is a weak entity of
  its sample test (24): a retest adds a result, and earlier ones stay.
- A sample can be in several collections (19) and is handed over to each department that tests it: the
  SampleHandover, a composite of the sample and the department (81).
- TestResult and TestReport are signed and changed through the approval entities (61, 62, 65, 66); the TestReport is
  what is released and delivered.

### Approval

[conceptual-approval.svg](conceptual-approval.svg)

- A Signature belongs to one document of one type: a TestResult, TestReport, Quotation or ChangeRequest (61 to 64). A
  ChangeRequest targets a TestResult, TestReport, Quotation or SaleOrder (65 to 68). Because the document can be of any
  of these types, each of these links is optional on the document side.
- An ApprovalLevel is a weak entity, a step of its chain (58). A Signature is strong: a person can sign or reject the
  same level of the same document again after withdrawing.
- Invoices have no approval chain and are not signed.
- A result's change request triggers the change request of its issued report (69).

### Sales

[conceptual-sales.svg](conceptual-sales.svg)

- An OrderLine is a weak entity of its SaleOrder (46): one parameter or one whole package (51) for one sample type
  (47). Its OrderLineSelections are composites of the line and each parameter it includes (48), with the way chosen
  (50).
- A SaleOrder has several Quotations (53), creates at most one TestRequest (54) and has a salesperson (82). A revised
  Quotation is a copy of the one it replaces, so Quotation is strong; [Not drawn](#not-drawn) says why that link
  is not drawn. Feedback is weak: one per order (56).
- An OrderTemplate keeps its source order (49) and its OrderTemplateLines, each one parameter or one package (85 to
  87).
- CancellationRequest and SupportRequest are not in the conceptual model.

### Finance

[conceptual-finance.svg](conceptual-finance.svg)

- An Invoice belongs to one SaleOrder (70). An advance invoice comes from at most one Quotation (71). An
  AdjustmentInvoice corrects one Invoice (72).
- A Payment pays one Invoice (73); its receipt and its gateway transaction are attributes.
- Tax applies to parameter and package prices (74, 75); the tax copied onto order lines and invoices is not drawn.

## Entities

| Entity | Vietnamese | Area | Kind | Identified by | Step | Source |
| --- | --- | --- | --- | --- | --- | --- |
| TestParameter | Chỉ Tiêu | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ParameterGroup | Nhóm Chỉ Tiêu | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleType | Loại Mẫu | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ParameterMethod | Cách Thử | Catalog | Composite | TestParameter + TestingMethod | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestingMethod | Phương Pháp Thử | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestingMethodStep | Bước Phương Pháp Thử | Catalog | Weak | TestingMethod | 6 | [Glossary](../../glossaries.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md), [Laboratory overview](../../functional/laboratory_module/overview.md) |
| SamplingRequirement | Yêu Cầu Lấy Mẫu | Catalog | Composite | TestingMethod + SampleType | 4 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work), [Glossary](../../glossaries.md) |
| TestingField | Lĩnh Vực Thử Nghiệm | Catalog | Strong | — | 7 | [Glossary](../../glossaries.md) |
| MeasurementUnit | Đơn Vị Đo | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Regulation | Quy Chuẩn | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| RegulationLimit | Giới Hạn Quy Chuẩn | Catalog | Composite | Regulation + TestParameter + SampleType | 4 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work), [Glossary](../../glossaries.md) |
| AccreditationCertificate | Giấy Chứng Nhận Công Nhận | Catalog | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| AccreditationScopeLine | Dòng Phạm Vi Công Nhận | Catalog | Weak | AccreditationCertificate | 6 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work), [Glossary](../../glossaries.md) |
| QualityRegistration | Hồ Sơ Đăng Ký Chất Lượng | Catalog | Strong | — | 7 | [Glossary](../../glossaries.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
| Department | Phòng Ban | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Person | Nhân Sự | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Machine | Máy | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| MachineService | Lịch Sử Bảo Trì Máy | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Location | Vị Trí | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| Subcontractor | Thầu Phụ | Resources | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| MachineBooking | Lịch Đặt Máy | Scheduling | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| PlanRevision | Phương Án Xếp Lại Lịch | Scheduling | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| OverTime | Làm Thêm Giờ | Scheduling | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| SubcontractDispatch | Phiếu Gửi Thầu Phụ | Scheduling | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| TestRequest | Yêu Cầu Thử Nghiệm | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleCollection | Giao Nhận Mẫu | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| Sample | Mẫu | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleTest | Chỉ Tiêu Của Mẫu | Testing | Composite | Sample + ParameterMethod | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleHandover | Bàn Giao Mẫu | Testing | Composite | Sample + Department | 4 | [Glossary](../../glossaries.md) |
| TestResult | Kết Quả Thử Nghiệm | Testing | Weak | SampleTest | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| SampleReturn | Trả Mẫu | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| TestReport | Phiếu Kết Quả | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ReportTemplate | Mẫu Phiếu Kết Quả | Testing | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| ApprovalChain | Chuỗi Phê Duyệt | Approval | Strong | — | 7 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| ApprovalLevel | Cấp Phê Duyệt | Approval | Weak | ApprovalChain | 6 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| Signature | Chữ Ký | Approval | Strong | — | 7 | [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) |
| ChangeRequest | Yêu Cầu Thay Đổi | Approval | Strong | — | 7 | [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) |
| Customer | Khách Hàng | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| ContactPerson | Người Liên Hệ | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| SaleOrder | Đơn Hàng | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderLine | Dòng Đơn Hàng | Sales | Weak | SaleOrder | 6 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderLineSelection | Lựa Chọn Cách Thử Trên Dòng Đơn | Sales | Composite | OrderLine + TestParameter | 6 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Quotation | Báo Giá | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| ServicePackage | Nhóm Dịch Vụ | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderTemplate | Đơn Thường Dùng | Sales | Strong | — | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| OrderTemplateLine | Dòng Đơn Thường Dùng | Sales | Weak | OrderTemplate | 6 | [Glossary](../../glossaries.md), [Sales](../../functional/ecommerce_module/features/sales.md) |
| CancellationRequest | Yêu Cầu Hủy | Sales | Strong | — | 7 | [Glossary](../../glossaries.md), [Sales](../../functional/ecommerce_module/features/sales.md) |
| SupportRequest | Yêu Cầu Hỗ Trợ | Sales | Strong | — | 7 | [Glossary](../../glossaries.md), [Sales](../../functional/ecommerce_module/features/sales.md) |
| Feedback | Đánh Giá | Sales | Weak | SaleOrder | 7 | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| Invoice | Hóa Đơn | Finance | Strong | — | 7 | [Glossary](../../glossaries.md), [Invoices](../../specs/invoices.md) |
| AdjustmentInvoice | Hóa Đơn Điều Chỉnh | Finance | Strong | — | 7 | [Glossary](../../glossaries.md), [Invoices](../../specs/invoices.md) |
| Payment | Thanh Toán | Finance | Strong | — | 7 | [Glossary](../../glossaries.md), [Payments](../../specs/payments.md) |
| Tax | Thuế | Finance | Strong | — | 7 | [Glossary](../../glossaries.md) |

## Relationships

`Card 1` is the number of `End 1` entities for one entity at the other end, `Card 2` the number of `End 2` entities for
one `End 1` entity: `1`, `0..1`, `0..*` or `1..*`. A relationship of three entities lists its second and third ends
and their numbers joined by `+`. A relationship named after a composite entity is drawn as that entity, with a
one-to-many line to each end: `1` at the end, and `M` at the composite when another end has many for that end. The
supporting relationship of a weak entity is the one with the entity in `Identified by`.

| # | End 1 | Card 1 | Relationship | Card 2 | End 2 | Source |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | SampleType | 0..1 | broadens | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 2 | TestParameter | 0..* | belongs to | 0..* | ParameterGroup | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 3 | TestParameter | 0..* | ParameterMethod | 1..* | TestingMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); a way has one parameter and one method, and every parameter has at least one way |
| 4 | TestingMethod | 1 | has | 0..* | TestingMethodStep | [Laboratory administrator](../../functional/laboratory_module/features/admin.md); step numbers are unique within a method |
| 5 | ParameterMethod | 0..* | performed in-house by | 0..1 | Department | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 6 | ParameterMethod | 0..* | performed externally by | 0..1 | Subcontractor | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 7 | ParameterMethod | 0..* | explicitly applies to | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); the sample-type applicability |
| 8 | TestingMethod | 0..* | SamplingRequirement | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work), [Glossary](../../glossaries.md) |
| 10 | AccreditationCertificate | 1 | contains | 1..* | AccreditationScopeLine | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 11 | AccreditationScopeLine | 0..* | covers | 1 | TestingMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 12 | AccreditationScopeLine | 0..* | covers | 1..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 13 | AccreditationScopeLine | 0..* | covers | 1..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 14 | Regulation | 0..* | applies to | 0..* | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 15 | Regulation | 0..* | RegulationLimit | 0..* + 0..* | TestParameter + SampleType | [Conceptual model](../../functional/conceptual-model.md#model-scope); unique per regulation, parameter and sample type |
| 16 | Customer | 1 | requests | 0..* | TestRequest | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 17 | TestRequest | 1 | includes | 1..* | Sample | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); confirming an order creates at least one expected sample |
| 18 | TestRequest | 1 | receives through | 0..* | SampleCollection | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 19 | SampleCollection | 0..* | records actual samples of | 0..* | Sample | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 20 | Sample | 0..* | has type | 1 | SampleType | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 21 | Sample | 0..* | optionally compares against | 0..1 | Regulation | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work) |
| 22 | Sample | 0..* | SampleTest | 1..* | ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#catalog-and-laboratory-work); every sample carries at least one sample test, whose way is required from creation |
| 23 | Sample | 0..* | is taken from | 0..1 | Location | [Laboratory overview](../../functional/laboratory_module/overview.md) |
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
| 38 | SubcontractDispatch | 0..* | sends | 1..* | SampleTest | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people), [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma); every dispatch sends at least one sample test |
| 39 | SubcontractDispatch | 0..* | sends to | 1 | Subcontractor | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 40 | Machine | 1 | has | 0..* | MachineService | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 41 | Person | 1 | has planned | 0..* | OverTime | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 42 | SampleCollection | 0..* | collected by | 1 | Person | [Conceptual model](../../functional/conceptual-model.md#bookings-and-people) |
| 43 | Customer | 0..1 | has | 0..* | ContactPerson | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory); a contact belongs to a customer or a subcontractor |
| 44 | Subcontractor | 0..1 | has | 0..* | ContactPerson | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory); a contact belongs to a customer or a subcontractor |
| 45 | Customer | 1 | places | 0..* | SaleOrder | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 46 | SaleOrder | 1 | selects | 1..* | OrderLine | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 47 | OrderLine | 0..* | for | 1 | SampleType | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 48 | OrderLine | 0..* | OrderLineSelection | 1..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory); one selection per parameter the line includes |
| 49 | SaleOrder | 1 | is saved as | 0..* | OrderTemplate | [Sales](../../functional/ecommerce_module/features/sales.md); a template retains its source order |
| 50 | OrderLineSelection | 0..* | chooses | 1 | ParameterMethod | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 51 | OrderLine | 0..* | buys whole | 0..1 | ServicePackage | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 52 | ServicePackage | 0..* | contains | 0..* | TestParameter | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 53 | SaleOrder | 1 | offers | 0..* | Quotation | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 54 | SaleOrder | 1 | creates | 0..1 | TestRequest | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 55 | Customer | 1 | reuses | 0..* | OrderTemplate | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
| 56 | SaleOrder | 1 | receives | 0..1 | Feedback | [Conceptual model](../../functional/conceptual-model.md#commerce-and-inventory) |
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
| 81 | Sample | 0..* | SampleHandover | 0..* | Department | [Glossary](../../glossaries.md); one per sample and department |
| 82 | Person | 0..1 | is salesperson of | 0..* | SaleOrder | [Sales](../../functional/ecommerce_module/features/sales.md); decides the order's tasks and visibility |
| 83 | TestingMethodStep | 0..* | is done in | 0..1 | Location | [Laboratory administrator](../../functional/laboratory_module/features/admin.md), [Laboratory overview](../../functional/laboratory_module/overview.md) |
| 84 | Location | 0..1 | contains | 0..* | Location | [Laboratory overview](../../functional/laboratory_module/overview.md) |
| 85 | OrderTemplate | 1 | retains | 1..* | OrderTemplateLine | [Sales](../../functional/ecommerce_module/features/sales.md); a template always retains at least one selection |
| 86 | OrderTemplateLine | 0..* | for | 0..1 | TestParameter | [Glossary](../../glossaries.md); one parameter or one package |
| 87 | OrderTemplateLine | 0..* | for | 0..1 | ServicePackage | [Glossary](../../glossaries.md); one parameter or one package |
| 88 | TestParameter | 0..* | is reported under | 1 | ParameterGroup | [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma); the group revenue reports count the parameter under, one of its groups |
| 89 | ParameterGroup | 0..1 | contains | 0..* | ParameterGroup | [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma); a sub-group has one parent group |
| 90 | SampleType | 0..* | minimum amount in | 0..1 | MeasurementUnit | [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma); the unit of the smallest amount of sample to collect |

## Not drawn

The candidates, and the relationships of the earlier conceptual ERD of the target design that this ERD does not
draw. A dash in Step means no step of [Method](#method) applies.

| Candidate | Step | Why |
| --- | --- | --- |
| AuditEntry, AuditChange, notifications and messages, DocumentLock, ScheduledJob, JobItem, JobRun, ArchiveFile, MobileDevice, PushDelivery | 1 | Technical |
| User, Role, RoleGrant, Permission, SigningCertificate, DigitalSignature | 1 | Login accounts, roles and certificates |
| Product, Combo, Contact, Employee, CalendarEvent, Attachment | 2 | Odoo records behind TestParameter, ServicePackage, Customer, ContactPerson, Subcontractor and Person |
| OrderSample, SchedulingPlan, Queue, MachineSchedule, PersonalSchedule, OutsourcingSuggestion, OutsourcingSchedule, ToDoList, Revenue, Outstanding, CashFlow, CollectionPerformance, SalesPipeline, SalesPerformance | 3 | Computed or a view |
| TestParameterSampleType, the sample types a parameter can be tested on | 3 | Worked out from the sample types of the parameter's active ways, never set by hand: relationships 3 and 7 |
| A link of OrderLine and SampleTest | 3 | A SampleTest keeps only its sample, parameter and way; its order line is found through SaleOrder, TestRequest and Sample (54, 17) and the OrderLineSelection of the same parameter (48) |
| TestRun, a batch of tests | 3 | A batch is the bookings that share one machine for the same interval, with ways of the same method, up to the machine's capacity: [Scheduling](../../specs/scheduling.md#sharing-a-machine) and the [Laboratory overview](../../functional/laboratory_module/overview.md#testing-work-and-scheduling) |
| ParameterMethodSampleType | 4 | Relationship 7; the glossary has no entry for the applicability of a way to a sample type |
| Receipt, PendingPayment, TaxRate, ParameterPrice, SubcontractCost, CustomerSalesTerms, NotificationContact, SampleLabel, LabCode | 5 | Attributes of Payment, Tax, TestParameter, ParameterMethod, Customer and ContactPerson |
| The ContactPerson who signs the handover record | 5 | The person who hands the samples over and signs is a name typed on the record (`handed_over_by_name` of HandoverRecord in [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma)), an attribute of SampleCollection |
| SigningProcess | 5 | The chain levels one document version keeps; document versions are out of scope |
| InvoiceLine | 6 | A line of Invoice; [Invoices](../../specs/invoices.md) gives it no relationships or rules |
| HandoverRecord | 2 | The handover record the customer signs, part of SampleCollection as the glossary says |
| Task, TaskType | 7 | The work queue of [SH-10](../../functional/shared.md#sh-10-tasks-and-to-do-list), not a business record |
| PaymentTransaction, ReconciliationDay | 7 | Payment gateway records, part of Payment |
| Team, stock, recipes, purchasing, laboratory files, onboarding | Scope | Inventory, Medilab Sync and Onboarding |
| Chemical, the methods that consume it and its unit | — | Not drawn, as the PO decided: chemicals are master data of the Laboratory module ([Inventory overview](../../functional/inventory_module/overview.md), [Laboratory administrator](../../functional/laboratory_module/features/admin.md)), but the ERD draws only the testing flow |
| The contact of a SaleOrder | — | Not drawn, as the PO decided |
| Quotation replaces Quotation | — | Each revision is a Quotation of the same SaleOrder (53), and a change after completion goes through a ChangeRequest (67); document versions are outside the [conceptual model](../../functional/conceptual-model.md#model-scope) |
| Signing of a SaleOrder | — | The Documents row of [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) has no order; an order is changed through a ChangeRequest (68) |

## Findings

Points where the [conceptual model](../../functional/conceptual-model.md) or the [glossary](../../glossaries.md)
disagree with the other documents. The ERD follows the column "ERD"; the documents are changed only where a row says so.

| Topic | What the documents say | ERD |
| --- | --- | --- |
| Signing and change requests | The conceptual model draws neither, although [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) signs test results, test reports, quotations above the thresholds and change requests, and [SH-07](../../functional/shared.md#sh-07-signed-documents-are-locked) changes results, reports, quotations and orders through change requests | ApprovalChain, ApprovalLevel, Signature and ChangeRequest, relationships 58 to 69 |
| Invoices and payments | The conceptual model leaves them to the E-commerce specifications; the glossary defines them and the Accountant works with them | Invoice, AdjustmentInvoice, Payment and Tax, relationships 70 to 75 |
| Other concepts of the glossary | QualityRegistration, TestingField, CancellationRequest, SupportRequest and the sample handover to departments are not in the conceptual model | Drawn, relationships 76 to 81 |
| Contact persons | The conceptual model makes every contact person belong to exactly one customer and to exactly one subcontractor at the same time | A contact person belongs to a customer or to a subcontractor, relationships 43 and 44 |
| Linked change requests | The text of the conceptual model links a result correction to the change request of the issued report, its diagram does not | Relationship 69 |
| Signed invoices | The Documents row of [SH-04](../../functional/shared.md#sh-04-signatures-and-digital-signing) listed invoices, but [Invoices](../../specs/invoices.md) and the [Accountant](../../functional/ecommerce_module/features/accountant.md) define no approval chain for them | Not signed, as the PO decided. Invoices are removed from the Documents row of SH-04 and from the Digital Signature Provider of the [use case diagram](../use-case-diagram/readme.md#external-systems) |
| SampleCollection and HandoverRecord | The glossary had both for the samples a customer hands over and signs for | SampleCollection only. The glossary entry HandoverRecord is merged into SampleCollection, whose handover record the customer signs |
| Payment | The glossary had no Payment entry, although PendingPayment and Receipt are defined through payments | Payment. The glossary entry Payment — Thanh Toán is added |
| QualityRegistration | The glossary covered the ways of testing of "a parameter"; the [Laboratory administrator](../../functional/laboratory_module/features/admin.md) covers "each covered parameter" | Many-to-many with ParameterMethod, relationship 79. The glossary entry now covers one or more parameters |
| AccreditationScopeLine | The glossary had no entry | The glossary entry AccreditationScopeLine — Dòng Phạm Vi Công Nhận is added |
| Order template contents | The conceptual model does not say what a template holds; the glossary has OrderTemplateLine and [Sales](../../functional/ecommerce_module/features/sales.md) keeps each template's source order | OrderTemplateLine, relationships 49 and 85 to 87 |
| Method steps and locations | The conceptual model has neither TestingMethodStep nor any Location link besides bookings; the [Laboratory overview](../../functional/laboratory_module/overview.md) has steps done in a location, samples taken from one and locations inside others | TestingMethodStep, relationships 4, 23, 83 and 84 |
| Parameter groups | The conceptual model has only the groups a parameter belongs to (2). [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma) gives each parameter a main group, "The group revenue reports count the parameter under; one of the parameter's groups", and each group an optional parent | Relationships 88 and 89. The conceptual model is not corrected |
| Method step label | The diagram of the [Laboratory overview](../../functional/laboratory_module/overview.md) labelled both the method-to-step and the step-to-location link "is done in" | "has" for relationship 4. The Laboratory overview diagram is corrected |
| Laboratory overview numbers | Its diagram let a scope line cover no parameter or sample type; the conceptual model says at least one | Follows the conceptual model, relationships 12 and 13. The Laboratory overview diagram is corrected |
| Parameters without a way | The conceptual model let a parameter have no way. The earlier conceptual ERD of the target design (`docs/target-design/erd/` of the previous repository) required at least one, and the PO confirmed it | Relationship 3. The conceptual model and the glossary entry TestParameter are corrected |
| Samples and collections | The earlier ERD gives each sample exactly one collection, because there a sample is created at its handover. Here expected samples are created when an order is confirmed, an insufficient sample collected again ([US-HD07](../../functional/laboratory_module/features/head-of-department.md)) goes through another collection, a signed handover record is corrected by a new one that keeps the old ([Sample Delivery Staff](../../functional/laboratory_module/features/sample-delivery-staff.md)), and `HandoverRecordSample` in [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma) lets a sample be on several records | Many-to-many, relationship 19, as the PO decided |
| Dispatches and sample tests | The conceptual model and the [Laboratory overview](../../functional/laboratory_module/overview.md) had a dispatch carry results, and the earlier ERD required at least one result per dispatch. But the results of an outsourced test are entered once its dispatch is sent, so a draft or sent dispatch has none, and [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma) links a dispatch to its sample tests and gives TestResult no dispatch | A dispatch sends at least one SampleTest, many-to-many (38), as the PO decided. The conceptual model, the Laboratory overview diagram and the glossary entry SubcontractDispatch are corrected; an outsourced result belongs to its sample test |

## Deviations from the proposal

Quotes are from the [capstone proposal](../proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx),
with their section; each is one sentence that can be searched for.

**Proposal concepts the ERD leaves out**

| Topic | Proposal | ERD | Documents |
| --- | --- | --- | --- |
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
| Handover between departments | *c) Functional Requirements → 4. Sampling and Reception → Sample Coding & Routing*: "Confirm sample handover between departments by QR scanning." | SampleHandover, a composite of Sample and Department (81), with no transfer from one department to another | [Laboratory overview](../../functional/laboratory_module/overview.md) |
| Discounts | *c) Functional Requirements → 2. Sales → Quotation & Order Management*: "Apply quotation discounts." | An attribute of OrderLine or Quotation | [Sales](../../functional/ecommerce_module/features/sales.md) |
| Quotation templates | *c) Functional Requirements → 2. Sales → Quotation & Order Management*: "Manage quotation templates." | OrderTemplate, a customer's saved order without prices | [Sales](../../functional/ecommerce_module/features/sales.md) |
| Receipts | *c) Functional Requirements → 9. Customer → Payment*: "Download receipt and invoice." | An attribute of Payment | [Payments](../../specs/payments.md) |
| Technical and reference standards | *c) Functional Requirements → 1. Administrator → Master Data & Service Catalog*: "Manage technical standards, regulations, specification limits, and reference-standard information." | A standard is the code of a TestingMethod; specification limits are the RegulationLimit composite (15) | [Laboratory administrator](../../functional/laboratory_module/features/admin.md) |
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
