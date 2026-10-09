# Features of: Tester

The tester, also called lab QA, runs the tests assigned to them on the laboratory's machines. Testers see samples only by their lab code, never the customer or the customer's name for the sample.

## I. User stories

### Planning

- **US-T01** As a tester, I want to see my testing tasks in my to-do list, soonest deadline first, so that I work on what is due first.
- **US-T02** As a tester, I want to schedule a test from the scheduler's recommendation of way of testing, machine and slot, so that it finishes before its due date.
- **US-T03** As a tester, I want to move or cancel my booking, so that my schedule matches what I can do.
- **US-T04** As a tester, I want to be reminded before a booking starts, so that I am at the machine on time.

### Results

- **US-T05** As a tester, I want to enter a result as a number in the unit of the way of testing or as a text, so that the measurement is recorded as it was made.
- **US-T06** As a tester, I want to set a result's conclusion, pass or fail, against the sample's regulation, so that the report states whether the sample complies.
- **US-T07** As a tester, I want to send my result for approval and sign it, so that the head of department can review it.
- **US-T08** As a tester, I want to retest when a result is rejected, so that the reported result is correct, while the rejected one stays on record.
- **US-T09** As a tester, I want to enter the results a subcontractor sends back for an outsourced test, so that they reach the report when the subcontractor does not enter them itself.

### Samples

- **US-T10** As a tester, I want to be reminded of samples whose retention ends soon and record their disposal, so that no sample is kept longer than needed.

## II. Feature details

### 1. Planning (US-T01 to US-T04)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling), [SH-10](../../shared.md#sh-10-tasks-and-to-do-list) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Recommendation | When a task is assigned to the tester, the scheduler recommends the way of testing and machine that finish it soonest within its due date. |
| Booking        | Scheduling takes the next free slot in the machine's queue: urgent tests first, then first in, first out.                |
| Adjusting      | Moving or cancelling a booking puts its slot back in the queue.                                                          |

Acceptance criteria:

- A scheduled booking appears on the tester's personal schedule, on the machine's schedule and in the tester's to-do list.
- A reminder arrives before the booking starts.
- A tester sees the lab code of a sample, not its customer or the customer's name for it.

### 2. Results (US-T05 to US-T09)

Follows [Results](../overview.md#results) and [Signing](../overview.md#signing).

| Rule        | Description                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| Limit copy  | A result copies the sample's regulation limit for its parameter, with its unit, when it is created.   |
| Measurement | A result takes the machine and start time from its booking; the tester can correct them. Entering the result marks the measurement done. |
| Conclusion  | The tester sets pass or fail when the sample has a regulation.                                       |
| Retest      | A retest adds a result; the earlier one is kept.                                                     |
| Task done   | The testing task is done when the reported result is approved.                                       |
| Outsourced  | The results of an outsourced test are entered by the subcontractor or by a lab QA; each result records who entered it. |

Acceptance criteria:

- A result entered for a booked test shows the booking's machine and start time, and the tester can correct them.
- A result entered on a sample with a regulation shows the copied limit and needs a conclusion before it is sent for approval.
- A rejected result stays on record, and the sample test goes back to testing.
- Approving the reported result closes the tester's testing task.

### 3. Samples (US-T10)

Follows [Reception](../overview.md#reception).

| Rule     | Description                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| Disposal | A sample is disposed of once it is not kept, its retention period is over or its request is cancelled. The method is the one entered on the sample, or else its sample type's disposal method. Disposal cannot be undone. |
| Reminder | A daily job gives testers a to-do listing samples whose retention ends within the reminder days, a system parameter (7 by default), or has ended. Running it again does not add a second to-do for the same sample. |

Acceptance criteria:

- Disposing of a sample with no method on it and none on its sample type is refused.
- A disposed sample cannot be disposed of again or changed back.
- A sample whose retention ends in 3 days appears on the reminder; a disposed one does not.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
