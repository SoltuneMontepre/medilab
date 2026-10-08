# Features of: Administrator

The administrator maintains the master data of the Laboratory module: test parameters, parameter groups, sample types, testing fields and methods, measurement units, regulations, quality registration dossiers, machines, chemicals and subcontractors. Quotations, the customer portal and testing all read the same master data. Prices, service packages and other commercial data are added by the E-commerce module; see the [E-commerce administrator](../../ecommerce_module/features/admin.md). The tables are drawn in [laboratory.prisma](../../../infrastructure/database/laboratory/laboratory.prisma).

## I. User stories

### Catalog

- **US-AD01** As an administrator, I want to maintain measurement units, sample types, parameter groups, test parameters, testing fields and testing methods, so that quotations and testing use one shared catalog.
- **US-AD02** As an administrator, I want to organise parameter groups into sub-groups, such as Organophosphates under Pesticides, so that choosing parameters from hundreds is not a flat list.
- **US-AD03** As an administrator, I want to organise sample types under broader types, such as Cabbage under Vegetables, so that filtering by a broad type also finds the parameters of its narrower types.
- **US-AD04** As an administrator, I want to define how each parameter is tested, with its method, unit, detection limits, department or subcontractor and accreditation, so that every test is done and reported the same way.
- **US-AD05** As an administrator, I want codes to be generated in a format I configure, so that codes are consistent and readable without typing them.
- **US-AD06** As an administrator, I want to archive master data instead of deleting it, so that past quotations and results keep their references while new ones cannot use it.
- **US-AD07** As an administrator, I want to maintain regulations with their limit per parameter, so that results can be compared with the limit that applies to the sample.
- **US-AD08** As an administrator, I want to maintain quality registration dossiers and the ways of testing they cover, so that reports print the right mark and the laboratory knows when a registration expires.

### Machines and chemicals

- **US-AD09** As an administrator, I want to maintain machines with their location, status, calibration and maintenance, so that tests only run on machines that are fit to use.
- **US-AD10** As an administrator, I want to record which parameter and method pairs each machine can run, so that a test is planned on a suitable machine.
- **US-AD11** As an administrator, I want to maintain chemicals with their identity, storage conditions and the methods that use them, so that the laboratory knows what each method needs.

### Subcontractors

- **US-AD12** As an administrator, I want to maintain subcontractors with their accreditation, contract and contact person, so that the laboratory only sends work to subcontractors it may use.

## II. Feature details

### 1. Catalog (US-AD01 to US-AD08)

| Rule                 | Description                                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Many links           | A test parameter can belong to several parameter groups and be tested on several sample types.                                                 |
| Lowest groups        | Parameters belong only to groups that have no sub-groups. A group that has parameters cannot be given sub-groups.                               |
| Main group           | Every parameter has one main group, which must be one of its groups. Reports per parameter group, such as revenue in E-commerce, count the parameter under its main group only. |
| Group tree           | A parameter group can have a parent group. Filtering by a group also finds the parameters of all its sub-groups. A group cannot be its own ancestor. |
| Sample type tree     | A sample type can have a broader parent type. Filtering by a sample type also finds the parameters of its narrower types. A type cannot be its own ancestor. |
| Way of testing       | Each parameter is tested by one or more pairs of parameter and testing method. Each pair has a unit, LOD and LOQ, and is tested either in-house or by one subcontractor. One pair per parameter is the default. |
| Testing method       | A method has its standard reference as its code, such as TCVN 6187-1:2009, and the title of the standard in each language. Each method belongs to one testing field, such as Chemistry or Microbiology. |
| Department           | An in-house pair of parameter and method names the department that tests it. Departments come from the active [people data source](../../../business/approval-and-signing-chain.md#people-data-source). |
| Accreditation        | Each pair of parameter and method is marked as within an ISO 17025 accreditation scope or not.                                                  |
| Detection limits     | LOD and LOQ are recorded per parameter and method pair, in that pair's unit.                                                                     |
| Codes                | Parameters, groups, sample types, dossiers and subcontractors get a code from a sequence when none is typed, such as `NCT.0001` for groups, `LM.0001` for sample types and `TP.0001` for subcontractors. The administrator can change the prefix and length; existing codes keep their value. A typed code must still be unique. |
| Sampling and storage | A sample type carries how to collect it, its minimum amount, storage conditions, whether and for how many days it is kept after testing, and how it is disposed of. A sample type without instructions has none; it does not use its parent's. |
| Unit conversion      | Each unit belongs to a category, such as mass concentration in liquid, and has a factor to the category's reference unit. Units convert only within their category. The system ships with common units and conversions, and suggests the category and factor of a new unit; the administrator confirms or edits them. |
| Converted values     | When a value is compared in another unit, such as a result against a regulation limit, the converted value is a suggestion that the user can edit before it is used. |
| Regulations          | A regulation, such as QCVN 6-1:2010/BYT, applies to sample types and sets at most one limit per parameter: a minimum, a maximum, or both, in a unit, or a text such as "Not detected". |
| Quality registration | A dossier is registered with an authority, has validity dates and covers parameter and method pairs. Its mark is printed after the name of each covered parameter on the report. A dossier counts as expired after its last valid day, and its mark is no longer printed. |
| Expiry warning       | Administrators are warned a number of days before a dossier expires and on the day it expires. The number of days is a system setting the administrator configures. |
| Permissions          | Only administrators create, edit and archive master data. Everyone else reads it.                                                                |
| Archiving            | Archived records do not appear in selection lists. Records in use cannot be deleted, only archived.                                              |

Acceptance criteria:

- Creating a group, sample type, parameter, dossier or subcontractor without a code fills the code from its sequence.
- Saving a code that already exists is refused with a message.
- A parameter in the sub-group Organophosphates appears when filtering by its parent group Pesticides.
- A parameter assigned to Cabbage appears when filtering by Vegetables.
- Making a group or sample type the parent of itself or of one of its ancestors is refused with a message.
- Adding a parameter to a group that has sub-groups, or a sub-group to a group that has parameters, is refused with a message.
- A parameter can be saved with several methods, groups and sample types, and the form shows them all.
- Saving a parameter whose main group is not one of its groups is refused with a message.
- A regulation cannot hold two limits for the same parameter.
- An archived record no longer appears when choosing records on a quotation or a parameter.

### 2. Machines and chemicals (US-AD09 to US-AD11)

| Rule            | Description                                                                                                                                   |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Machine         | A machine has a code, name, model, manufacturer, serial number, location and status: in use, under repair or retired.                       |
| Service history | Each calibration, maintenance or repair is recorded with its date, who did it, its certificate or report number and when the next one is due. Records are kept, not overwritten. |
| Calibration     | A machine whose next calibration date has passed cannot be used until a new calibration is recorded.                                          |
| Maintenance     | A machine can have a maintenance interval in days; its next maintenance date follows from the latest maintenance record.                      |
| Machine use     | A machine is linked to the parameter and method pairs it can run.                                                                             |
| Chemical        | A chemical has a code, name, CAS number, formula, grade, storage conditions and the testing methods that use it. Stock, expiry, suppliers and how much of a chemical one test uses belong to the [Inventory module](../../../business/module-boundaries.md). |

Acceptance criteria:

- A machine whose next calibration date is in the past cannot be chosen to run a test.
- Recording a calibration with a new due date makes the machine usable again.
- A machine that is under repair or retired cannot be chosen to run a test.
- A testing method shows the chemicals it uses, and a chemical shows the methods that use it.

### 3. Subcontractors (US-AD12)

A subcontractor is a company contact with the details the laboratory needs to send it work. Its name, address and people come from the contact.

| Rule                  | Description                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------- |
| Expired accreditation | A subcontractor whose accreditation has expired cannot be chosen until its expiry date is renewed. |
| No expiry date        | A subcontractor with no accreditation expiry date can be chosen.                                  |
| Contact person        | A subcontractor has a default contact person, usually one of its people; any person contact is allowed. |
| Choosing the tester   | For each order, the scheduling system suggests which way of testing is used, in-house or by which subcontractor. The laboratory usually decides and can change it. |
| Disclosure            | Results tested by a subcontractor are marked as subcontracted on the report.                       |

Acceptance criteria:

- A subcontractor with an accreditation expiry date in the past cannot be chosen on a parameter and method pair.
- A subcontractor with no expiry date can be chosen.
- An archived subcontractor does not appear in selection lists.

## III. Related documents

- [Laboratory overview](../overview.md)
- [E-commerce administrator](../../ecommerce_module/features/admin.md)
- [Approval and signing chain](../../../business/approval-and-signing-chain.md)
- [Module boundaries](../../../business/module-boundaries.md)
- [Database diagram](../../../infrastructure/database/laboratory/laboratory.prisma)
- [Glossaries](../../../glossaries.md)
