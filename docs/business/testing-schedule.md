# Testing schedule

- Sales states the date the customer expects the results. The laboratory plans every test of the request to finish a safety margin of days before that date, kept for handling incidents. The margin is a system parameter. A due date is worked out when the sample test is created or the request's expected date changes; changing the margin does not change due dates already worked out.
- Before an order is taken, the laboratory estimates when its results can be returned and checks whether an earlier date the customer asks for can be met; an accepted priority order makes its tests urgent.
- A test is urgent when its planned finish date is within a number of hours set as a system parameter, or when the laboratory marks it urgent with a reason.
- Tests waiting for a machine are scheduled urgent first, then in the order they joined the queue.
- A test with no booking that finishes before its due date is at risk; its tester and head of department are told.
- The head of department can bump an urgent test ahead of bookings that have not started, and decides what happens to the tests the bump would make late.
- When no machine that can run a test is available, or none can finish it in time, the test is outsourced to a subcontractor. The head of department can also outsource a test straight away in an emergency.
- Work waiting for someone is a task. Every task goes through the same statuses; the state of the work belongs to its document. A testing task is done when its result is approved.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#testing-work-and-scheduling)
- [Shared technical features](../functional/shared.md#sh-10-tasks-and-to-do-list)
