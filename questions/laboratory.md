# Laboratory questions

- **Zero limits (US-AD07).** Odoo stores an empty number as 0, so a regulation limit of exactly 0, such as 0 CFU/250 mL, reads as "no limit" and is entered as the text "Not detected" instead. Does any regulation need a numeric limit of 0, for example so results can be compared with it automatically?
- **Changing a due date.** A sample test's due date can be changed by hand. Who may change it, and does it keep the changed date when the request's expected date changes? (blocks US-HD05)
- **Due date check.** A due date falls on a weekday and the scheduler checks that a slot is free or can be made free. Do public holidays count as non-working days, does the check block saving or only warn, may it move the bookings of other tests, and does it suggest the earliest date that can be met? (blocks US-HD05)
- **Team work.** Departments can be split into teams. Do testing tasks also queue by team, and does the team lead assign them instead of the head of department? (blocks US-AD13)
- **Who maintains customers.** A customer's details are an Odoo contact, and Odoo lets only its contact managers create and edit contacts, so for now only administrators create and edit customers. Should sales get Odoo's contact creation group, or should a customer write its contact with full rights once the customer permission is checked, as people do? (blocks US-S03)
- **Cancelling during testing.** A test request can be cancelled while testing, but the lifecycles let only expected, received and testing samples, and waiting, assigned and testing sample tests, be cancelled. What happens to a sample on hold or awaiting approval, and to a test outsourced or with a result entered, when its request is cancelled? For now they keep their status. (US-SD06, US-S17)
- **Every test cancelled.** When the head of department cancels every sample test of a sample, nothing is left to test or report. Is the sample cancelled too, and its test request once all its samples are? For now the sample keeps its status. (US-HD09)
- **Correcting a reported result.** A change request on a result whose report is already issued creates a new result version, but the issued report keeps the old value until someone raises a change request on the report too. Should approving the new result version reissue the report by itself, and should a change request on a result be refused while its report waits for the lab head's signature? For now the two are separate change requests. And when the lab head rejects a new report version and the results sent back are approved again, its request is already reported, so no new signing task is created: should it be? (US-T11, US-LH03)

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
