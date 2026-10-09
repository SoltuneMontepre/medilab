# Features of: Sample receiver

The sample receiver takes in the samples that arrive at the laboratory, records their state, and hands them over to the departments that test them.

## I. User stories

- **US-SR01** As a sample receiver, I want to see the samples expected for each test request, so that I know what should arrive.
- **US-SR02** As a sample receiver, I want to record a sample's receipt with the amount, its condition and where it is stored, so that its state on arrival is on record.
- **US-SR03** As a sample receiver, I want to reject a sample that cannot be tested, with the reason, so that nobody works on it.
- **US-SR04** As a sample receiver, I want to put an insufficient sample on hold and report it to the head of department, so that it can be collected again.
- **US-SR05** As a sample receiver, I want to hand a received sample over to each department that tests it, so that every department knows it has the sample.

## II. Feature details

### 1. Reception (US-SR01 to US-SR05)

Follows the reception rules and the sample lifecycle in the [Laboratory overview](../overview.md#reception).

| Rule         | Description                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Receipt      | Receipt records when and by whom the sample was received, the amount received, its condition (good, damaged or insufficient) with a note, and where it is stored. |
| Testing tasks | Receiving a sample creates a testing task for each of its sample tests in the queue of the department that does the work.   |
| Handover     | The sample is handed over to each department that tests it; the department records when and by whom it received it.         |

Acceptance criteria:

- Recording a sample's receipt sets it to received and creates its testing tasks in each department's queue.
- A rejected sample keeps its condition note and gets no testing tasks.
- An insufficient sample is on hold, and its head of department is told.
- A sample handed over to two departments shows both handovers and which department has received it.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Sample collector](sample-collector.md)
- [Head of department](head-of-department.md)
