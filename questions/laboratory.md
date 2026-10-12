# Laboratory questions

- **Zero limits (US-AD07).** Odoo stores an empty number as 0, so a regulation limit of exactly 0, such as 0 CFU/250 mL, reads as "no limit" and is entered as the text "Not detected" instead. Does any regulation need a numeric limit of 0, for example so results can be compared with it automatically?
- **Changing a due date.** A sample test's due date can be changed by hand. Who may change it, and does it keep the changed date when the request's expected date changes? (blocks US-HD05)
- **Due date check.** A due date falls on a weekday and the scheduler checks that a slot is free or can be made free. Do public holidays count as non-working days, does the check block saving or only warn, may it move the bookings of other tests, and does it suggest the earliest date that can be met? (blocks US-HD05)
- **Team work.** Departments can be split into teams. Do testing tasks also queue by team, and does the team lead assign them instead of the head of department? (blocks US-AD13)

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
