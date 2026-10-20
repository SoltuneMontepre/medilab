# Scheduling questions

- **No subcontractor either.** When a test cannot be done in time in-house and its parameter has no subcontracted way of testing, what happens?
- **Bumping outside working hours.** Can a bumped test take a slot outside its tester's working hours? Some companies keep to working hours strictly and others do not, so ideally both are supported, for example as a setting.
- **Periodic maintenance.** A machine has a maintenance interval and a next maintenance date, but nobody is reminded, there is no maintenance schedule, and a machine overdue for maintenance can still be booked. Should maintenance remind someone, reserve the machine's time on its schedule, and block bookings when overdue, as calibration does? (US-AD09)
- **Machine breaks during a run.** When a machine becomes under repair, its scheduled bookings are planned again, but a running booking is not covered. Is the running test cancelled, retested from the start, or moved to another machine, and is more sample needed?
- **Absent testers.** A tester's leave or sick day is not linked to their bookings, so the head of department moves them by hand. Should Odoo Time Off put an absent person's bookings back in the queue automatically?
- **Late tests.** When a test will miss its due date, for example after a bump the head lets run late, who is told: the head, sales, the customer? Does the date the customer expects change?
- **Room unavailable.** A bookable room can be closed or under maintenance. Can a room be made unavailable for a time, and are the tests booked in it planned again as for a machine?
- **Deadline risk notice.** A tester and head are told once when a test becomes at risk. Should they be reminded again, for example daily, until it is resolved?
- **Machine heads-up days.** The warning starts 7 days before a calibration or maintenance is due and lasts 7 days after a repair. Are those the right windows, and should calibration and maintenance have different ones?
- **Return estimate for outsourced parameters.** A parameter only a subcontractor tests is left out of the estimate. Should subcontractors have a usual turnaround so the estimate covers them?
## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
- [Shared technical features](../docs/functional/shared.md)
