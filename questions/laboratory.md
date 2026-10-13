# Laboratory questions

- **Zero limits (US-AD07).** Odoo stores an empty number as 0, so a regulation limit of exactly 0, such as 0 CFU/250 mL, reads as "no limit" and is entered as the text "Not detected" instead. Does any regulation need a numeric limit of 0, for example so results can be compared with it automatically?
- **Changing a due date.** A sample test's due date can be changed by hand. Who may change it, and does it keep the changed date when the request's expected date changes? (blocks US-HD05)
- **Due date check.** A due date falls on a weekday and the scheduler checks that a slot is free or can be made free. Do public holidays count as non-working days, does the check block saving or only warn, may it move the bookings of other tests, and does it suggest the earliest date that can be met? (blocks US-HD05)
- **Team work.** Departments can be split into teams. Do testing tasks also queue by team, and does the team lead assign them instead of the head of department? (blocks US-AD13)
- **Who maintains customers.** A customer's details are an Odoo contact, and Odoo lets only its contact managers create and edit contacts, so for now only administrators create and edit customers. Should sales get Odoo's contact creation group, or should a customer write its contact with full rights once the customer permission is checked, as people do? (blocks US-S03)
- **Cancelling during testing.** A test request can be cancelled while testing, but the lifecycles let only expected, received and testing samples, and waiting, assigned and testing sample tests, be cancelled. What happens to a sample on hold or awaiting approval, and to a test outsourced or with a result entered, when its request is cancelled? For now they keep their status. (US-SD06, US-S17)
- **Deleting ways of testing.** The Ways of Testing list on the parameter form only archives a pair. The documents still let a pair that nothing refers to be deleted, and the Delete ways of testing permissions are still shipped, but no screen offers deleting one, so only the API can. Should a screen offer deleting an unused pair, or should the delete action and its permissions be removed? (US-AD06)

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
