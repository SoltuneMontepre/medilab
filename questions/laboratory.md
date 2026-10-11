# Laboratory questions

- **Zero limits (US-AD07).** Odoo stores an empty number as 0, so a regulation limit of exactly 0, such as 0 CFU/250 mL, reads as "no limit" and is entered as the text "Not detected" instead. Does any regulation need a numeric limit of 0, for example so results can be compared with it automatically?
- **Team work.** Departments can be split into teams. Do testing tasks also queue by team, and does the team lead assign them instead of the head of department? (blocks US-AD13)
- **Who maintains customers.** A customer's details are an Odoo contact, and Odoo lets only its contact managers create and edit contacts, so for now only administrators create and edit customers. Should sales get Odoo's contact creation group, or should a customer write its contact with full rights once the customer permission is checked, as people do? (blocks US-S03)
- **Cancelling during testing.** A test request can be cancelled while testing, but the lifecycles let only expected, received and testing samples, and waiting, assigned and testing sample tests, be cancelled. What happens to a sample on hold or awaiting approval, and to a test outsourced or with a result entered, when its request is cancelled? For now they keep their status. (US-SD06, US-S17)

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
