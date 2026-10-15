# Features of: Administrator

The administrator maintains the master data of the Laboratory module: test parameters, parameter groups, sample types, testing fields and methods, measurement units, regulations, quality registration dossiers, machines, chemicals and subcontractors. Quotations, the customer portal and testing all read the same master data. Prices, service packages and other commercial data are added by the E-commerce module; see the [E-commerce administrator](../../ecommerce_module/features/admin.md). The tables are drawn in [laboratory.prisma](../../../infrastructure/database/laboratory/laboratory.prisma).

## I. User stories

### Catalog

- **US-AD01** As an administrator, I want to maintain measurement units, sample types, parameter groups, test parameters, testing fields and testing methods, so that quotations and testing use one shared catalog.
- **US-AD02** As an administrator, I want to organise parameter groups into sub-groups, such as Organophosphates under Pesticides, so that choosing parameters from hundreds is not a flat list.
- **US-AD03** As an administrator, I want to organise sample types under broader types, such as Cabbage under Vegetables, so that filtering by a broad type also finds the parameters of its narrower types.
- **US-AD04** As an administrator, I want to define how each parameter is tested, with its method, unit, detection limits, department or subcontractor, so that every test is done and reported the same way.
- **US-AD05** As an administrator, I want codes to be generated in a format I configure, so that codes are consistent and readable without typing them.
- **US-AD06** As an administrator, I want to delete master data that nothing refers to and archive master data that only finished documents still use, so that selection lists stay short while past quotations and results keep their references.
- **US-AD07** As an administrator, I want to maintain regulations with their limit per parameter, so that results can be compared with the limit that applies to the sample.
- **US-AD08** As an administrator, I want to maintain quality registration dossiers and the ways of testing they cover, so that reports print the right mark and the laboratory knows when a registration expires.
- **US-AD26** As an administrator, I want to define the steps of a testing method, each with its number, how long it takes, what to do and a note, so that everyone in the laboratory follows the same procedure.
- **US-AD27** As an administrator, I want to define the locations of the company's premises as a tree with a code and name, optionally belonging to a department and bookable, so that the laboratory can name every place where work is done.
- **US-AD28** As an administrator, I want to record the ISO 17025 accreditation certificates of the laboratory and create the testing methods they list in one go, so that the methods of an accreditation scope are entered once instead of one by one.

### Machines and chemicals

- **US-AD09** As an administrator, I want to maintain machines with their location, status, calibration and maintenance, so that tests only run on machines that are fit to use.
- **US-AD10** As an administrator, I want to record which parameter and method pairs each machine can run, so that a test is planned on a suitable machine.
- **US-AD11** As an administrator, I want to maintain chemicals with their identity, storage conditions and the methods that use them, so that the laboratory knows what each method needs.

### Subcontractors

- **US-AD12** As an administrator, I want to maintain subcontractors with their accreditation, contract and contact person, so that the laboratory only sends work to subcontractors it may use.

### People and signing

- **US-AD13** As an administrator, I want to maintain departments, their teams and people with their contact details, login account, department and team, so that everyone who works for the laboratory is recorded in one place.
- **US-AD14** As an administrator, I want to maintain the approval chain of each document type, for signing it and for change requests on it, so that every document is signed by the right roles in the right order.
- **US-AD15** As an administrator, I want to group permissions into roles, assign roles to people and give a person extra permissions, so that everyone can do exactly their part of the work.
- **US-AD16** As an administrator, I want to choose where the tasks of each task type go and their default deadline, so that work reaches the right people automatically.

## II. Feature details

### 1. Catalog (US-AD01 to US-AD08, US-AD26 to US-AD28)

| Rule                 | Description                                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Many links           | A test parameter can belong to several parameter groups and be tested on several sample types.                                                 |
| Lowest groups        | Parameters belong only to groups that have no sub-groups. A group that has parameters cannot be given sub-groups.                               |
| Main group           | Every parameter has one main group, which must be one of its groups. Reports per parameter group, such as revenue in E-commerce, count the parameter under its main group only. |
| Group tree           | A parameter group can have a parent group. Filtering by a group also finds the parameters of all its sub-groups. A group cannot be its own ancestor. |
| Sample type tree     | A sample type can have a broader parent type. Filtering by a sample type also finds the parameters of its narrower types. A type cannot be its own ancestor. |
| Way of testing       | Each parameter is tested by one or more pairs of parameter and testing method. Each pair has a unit, LOD and LOQ, and is tested either in-house or by one subcontractor. One pair per parameter is the default. |
| Testing method       | A method has its standard reference as its code, such as TCVN 6187-1:2009, and the title of the standard in each language. Each method belongs to one testing field, such as Chemistry or Microbiology. |
| Method steps         | A testing method has an ordered list of steps. A step has a number, how long it takes in minutes, what to do, an optional location where it is done and an optional note. Step numbers are unique within a method. The steps belong to the method, so every department and subcontractor way of testing that uses the method shows the same steps. |
| Location             | A location is any place in the company's premises, such as a floor, a working room, a manager's office, a meeting room, a bench, an area or a sampling point, with a unique code, a name in each language and an optional image. It can have a parent location, so locations form a tree of any depth, such as building, floor, room and bench, and can name the department that uses it. A location can be marked bookable, so people can book it on their calendar ([SH-11](../../shared.md#sh-11-schedules-and-reminders)). The administrator defines the layout; the system ships none. A location is not tied to a machine: it names any place work is done, such as a fume hood, a water point or a preparation room; stores and the locations inside them are Inventory stock locations. A location with an image is a map: each location inside it can be placed at a point on that image. The map shows the locations inside it at their points. |
| Accreditation certificate | An accreditation certificate of the laboratory has a number, the body that issued it, validity dates and the testing methods of its scope. A method can be on several certificates. |
| Import from certificate | From a certificate, the administrator enters the list of methods in its scope as standard code and title, and chooses one testing field for the list. A code that already exists is linked to the certificate unchanged; any other creates a testing method in the chosen field with no steps, and links it. Titles are entered in the language of the list; other languages are added later on the method. Nothing is saved when any row has no code or title. |
| Department           | An in-house pair of parameter and method names the department that tests it. Departments are maintained by the administrator (US-AD13). |
| Accreditation        | An in-house pair of parameter and method is within the ISO 17025 accreditation scope while its method is on an accreditation certificate that is valid that day. It is worked out, not set by hand: it changes when a certificate's methods or dates change, and a [scheduled job](../../shared.md#sh-09-scheduled-tasks) updates it each day as certificates start and expire. A certificate without a start or end date is valid from or until any date. A subcontracted pair is never within the laboratory's scope.                                                  |
| Detection limits     | LOD and LOQ are recorded per parameter and method pair, in that pair's unit.                                                                     |
| Codes                | Parameters, groups, sample types, dossiers, subcontractors, customers, test requests and subcontract dispatches get a code from a sequence when none is typed, such as `CT.0001` for parameters, `NCT.0001` for groups, `LM.0001` for sample types, `HS.0001` for dossiers, `TP.0001` for subcontractors, `KH.0001` for customers and `YC.2026.0001` for test requests, numbered again each year. Samples get their lab code from a sequence, such as `PTN.2026.0001`. The administrator can change the prefix and length; existing codes keep their value. A typed code must still be unique. |
| Sampling and storage | A sample type carries how to collect it, its minimum amount, storage conditions, whether and for how many days it is kept after testing, and how it is disposed of. A sample type without instructions has none; it does not use its parent's. |
| Unit conversion      | Each unit belongs to a category, such as mass concentration in liquid, and has a factor to the category's reference unit. Units convert only within their category. The system ships with common units and conversions, and suggests the category and factor of a new unit; the administrator confirms or edits them. |
| Converted values     | When a value is compared in another unit, such as a result against a regulation limit, the converted value is a suggestion that the user can edit before it is used. |
| Regulations          | A regulation, such as QCVN 6-1:2010/BYT, applies to sample types and sets at most one limit per parameter: a minimum, a maximum, or both, in a unit, or a text such as "Not detected" without a unit. A minimum or a maximum may be empty or any number, including 0. A limit has at least one of them set. |
| Quality registration | A dossier is registered with an authority, has validity dates and covers parameter and method pairs. Its mark is printed after the name of each covered parameter on the report. A dossier counts as expired after its last valid day, and its mark is no longer printed. |
| Expiry warning       | Administrators are warned a number of days before a dossier expires and on the day it expires. The number of days is a system setting the administrator configures. |
| Permissions          | Creating, editing, archiving and deleting master data are permissions the administrator holds and can give to other roles and people. Everyone who works for the laboratory reads it. |
| Archiving            | Follows [Archiving and deleting](../../../business/archiving-and-deleting.md). Test parameters, parameter and method pairs and subcontractors are archived, never deleted. The Ways of Testing list on the parameter form archives and restores a pair with its Active toggle. Once a pair is archived, a new pair for the same parameter, method and subcontractor is allowed. |
| Deleting             | Units, unit categories, testing fields, testing methods, parameter groups, sample types, regulations, quality registration dossiers, accreditation certificates, locations, machines and chemicals can also be deleted when nothing refers to them, such as a sample type no parameter, sample or regulation names. |

Acceptance criteria:

- Creating a group, sample type, parameter, dossier, subcontractor or customer without a code fills the code from its sequence.
- Saving a code that already exists is refused with a message.
- A parameter in the sub-group Organophosphates appears when filtering by its parent group Pesticides.
- A parameter assigned to Cabbage appears when filtering by Vegetables.
- Making a group or sample type the parent of itself or of one of its ancestors is refused with a message.
- Adding a parameter to a group that has sub-groups, or a sub-group to a group that has parameters, is refused with a message.
- A parameter can be saved with several methods, groups and sample types, and the form shows them all.
- Saving a parameter whose main group is not one of its groups is refused with a message.
- A method can be saved with several steps, and the form lists them by step number.
- Saving two steps of one method with the same number, or a step without a number, how long or what to do, is refused with a message.
- Importing a list of 30 methods creates the ones that do not exist, links all 30 to the certificate, and leaves the 5 that already existed unchanged.
- Importing a list with a row without a code or title is refused with a message and creates nothing.
- An in-house pair whose method is on a valid certificate is accredited; the day after the certificate's last valid day, it no longer is.
- A subcontracted pair is not accredited, even when its method is on a valid certificate.
- A certificate can be saved with several methods, and a method with several certificates.
- A location placed on its parent's image shows as a point on the parent's map.
- A location can be saved under a parent location, with or without a department and an image, and marked bookable or not.
- A location that a step, a sample, a machine, a booking or another module refers to cannot be deleted, only archived.
- A location cannot be its own ancestor, and two locations cannot share a code; both are refused with a message.
- A regulation cannot hold two limits for the same parameter.
- An archived record no longer appears when choosing records on a quotation or a parameter.
- A unit used by an active parameter and method pair cannot be archived or deleted; the message lists the pairs.
- A sample type that only finished samples use can be archived but not deleted.
- Saving an in-house pair without a department is refused.
- Saving the same parameter, method and subcontractor as a pair that is still active is refused. Once that pair is archived, the same combination can be saved again.
- A test parameter, a parameter and method pair or a subcontractor cannot be deleted, only archived, not even when nothing refers to it.
- The Ways of Testing list on the parameter form does not offer deleting a pair; a pair that is no longer used is archived with its Active toggle and can be restored the same way.

### 2. Machines and chemicals (US-AD09 to US-AD11)

| Rule            | Description                                                                                                                                   |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Machine         | A machine has a code, name, model, manufacturer, serial number, location and status: in use, under repair or retired. The location is chosen from the locations, such as the bench the machine stands on.                       |
| Service history | Each calibration, maintenance or repair is recorded with its date, who did it, its certificate or report number and when the next one is due. A record can be edited, and the changes are kept in the audit trail. |
| Calibration     | A machine whose next calibration date has passed cannot be used until a new calibration is recorded.                                          |
| Maintenance     | A machine can have a maintenance interval in days; its next maintenance date follows from the latest maintenance record.                      |
| Machine use     | A machine is linked to the parameter and method pairs it can run, with the minutes one run takes.                                                                             |
| Chemical        | A chemical has a code, name, CAS number, formula, grade, storage conditions and the testing methods that use it. Stock, expiry, suppliers and how much of a chemical one test uses belong to the [Inventory module](../../../business/module-boundaries.md). |

Acceptance criteria:

- A machine whose next calibration date is in the past cannot be chosen to run a test.
- Recording a calibration with a new due date makes the machine usable again.
- A machine that is under repair or retired cannot be chosen to run a test.
- A testing method shows the chemicals it uses, and a chemical shows the methods that use it.
- A machine with a queued, scheduled or running booking cannot be archived; once its bookings are done or cancelled, it can be archived.
- A machine that is in use, has any booking or service record, or is linked to a parameter and method pair cannot be deleted.
- A chemical cannot be deleted while a testing method uses it.

### 3. Subcontractors (US-AD12)

A subcontractor is a company contact with the details the laboratory needs to send it work. Its name, address and people come from the contact.

| Rule                  | Description                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------- |
| Expired accreditation | A subcontractor whose accreditation expiry date is in the past cannot be chosen on a parameter and method pair until the date is renewed. The selection list offers only subcontractors that can be chosen, and saving a pair with one that cannot is refused with a message naming it, so the API follows the same rule as the interface. |
| Kept after expiry     | The rule applies when a subcontractor is chosen. A pair saved while its subcontractor was valid keeps it after the accreditation expires. |
| No expiry date        | A subcontractor with no accreditation expiry date can be chosen.                                  |
| Contact person        | A subcontractor has a default contact person, usually one of its people; any person contact is allowed. |
| Choosing the tester   | For each order, the scheduling system suggests which way of testing is used, in-house or by which subcontractor. The laboratory usually decides and can change it. |
| Disclosure            | Results tested by a subcontractor are marked as subcontracted on the report.                       |

Acceptance criteria:

- A subcontractor with an accreditation expiry date in the past cannot be chosen on a parameter and method pair; saving the pair is refused with a message naming the subcontractor.
- A subcontractor with no expiry date, or whose expiry date is today or later, can be chosen.
- A subcontractor whose expiry date is renewed can be chosen again.
- A pair keeps its subcontractor after the accreditation expires, and its other fields can still be edited.
- An archived subcontractor does not appear in selection lists, and saving a pair with one is refused with a message naming it.

### 4. People and signing (US-AD13 to US-AD16)

Follows [Approval and signing chain](../../../business/approval-and-signing-chain.md).

| Rule              | Description                                                                                                                       |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Departments       | The administrator creates the laboratory's departments and puts people in them. Departments are Odoo's employee departments, and the head of a department is its manager. |
| Teams             | A department can be split into teams (tổ), each with its team lead. A team is a department under its department, and its manager is its team lead. A person can belong to one team of their department. |
| Person            | Each person has an Odoo employee. Their details are the employee's work contact. A person who signs in is linked to their Odoo user, which holds only the login. |
| Permissions       | A permission is an action on a document type: read, create, edit, archive, delete or sign. Each covers every record, only those of the person's department or only those of the person's team. |
| Roles             | A role is a set of permissions. The administrator assigns roles to people and can give a person extra permissions directly. |
| Approval chain    | Each document type has one chain for signing it and one for change requests on it.                                               |
| Levels            | A chain has levels signed in order. Each level names one of the roles that signs it, whether the signer must belong to the department that did the work, and whether it can reject. |
| Task types        | Task types come with the modules, each with its trigger and the document and action its tasks open. The administrator chooses where new tasks go, a department queue, the holders of a role or a person, and the default deadline. See [SH-10](../../shared.md#sh-10-tasks-and-to-do-list). |
| Archiving         | Follows [Archiving and deleting](../../../business/archiving-and-deleting.md). Roles are never archived. |
| Deleting          | The administrator can delete a department, team, person, role or approval chain when nothing refers to it: a department with no teams, people, parameter and method pairs or tasks; a team with no people; a person with no tasks, bookings or signatures; a role that no person holds and no approval level or task type names; a chain none of whose levels has been signed. Deleting a person also removes their roles, a role its permissions, and a chain its levels. |

Acceptance criteria:

- A department created by the administrator can be named on a parameter and method pair.
- A document type cannot have two chains for the same purpose.
- A chain cannot have two levels in the same position.
- A person without a permission for an action, through a role or directly, cannot take it and does not see it in the interface.
- A permission given to a person directly adds to the permissions of their roles.
- A permission limited to the person's department hides the records of other departments.
- A permission limited to the person's team hides the records of other teams.
- A person's team must belong to their department.
- A department, person, role or approval chain that nothing refers to can be deleted.
- Deleting a department that has people, parameter and method pairs or tasks, or a role that a person holds or an approval level or task type names, is refused with a message listing them.
- A role cannot be archived; it is removed from people, approval levels and task types, then deleted.
- A person who has signed a document, or a chain with a signed level, cannot be deleted; the message lists the signatures.
- A task type cannot be created, archived or deleted on the screen; only its route, role and default deadline change.

## III. Related documents

- [Laboratory overview](../overview.md)
- [E-commerce administrator](../../ecommerce_module/features/admin.md)
- [Approval and signing chain](../../../business/approval-and-signing-chain.md)
- [Module boundaries](../../../business/module-boundaries.md)
- [Database diagram](../../../infrastructure/database/laboratory/laboratory.prisma)
- [Glossaries](../../../glossaries.md)
