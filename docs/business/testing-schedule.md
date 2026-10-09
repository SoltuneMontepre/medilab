# Testing schedule

- Sales states the date the customer expects the results. The laboratory plans every test of the request to finish a safety margin of days before that date, kept for handling incidents. The margin is a system parameter.
- A test is urgent when its planned finish date is within a number of hours set as a system parameter.
- Tests waiting for a machine are scheduled urgent first, then in the order they joined the queue.
- When no machine that can run a test is available, or none can finish it in time, the test is outsourced to a subcontractor.
- Work waiting for someone is a task. Every task goes through the same statuses; the state of the work belongs to its document. A testing task is done when its result is approved.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#testing-work-and-scheduling)
- [Shared technical features](../functional/shared.md#sh-10-tasks-and-to-do-list)
