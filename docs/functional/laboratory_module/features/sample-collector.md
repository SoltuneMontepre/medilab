# Features of: Sample collector

The sample collector collects samples at the customer's site when a sample collection task is scheduled for them, including when a sample has to be collected again.

## I. User stories

- **US-SC01** As a sample collector, I want to see my sample collection tasks on my schedule and to-do list with their time and place, so that I know where to go and when.
- **US-SC02** As a sample collector, I want to be reminded before a collection starts, so that I am not late.
- **US-SC03** As a sample collector, I want to mark a collection task done when the samples are collected, so that the laboratory expects them.

## II. Feature details

### 1. Collecting samples (US-SC01 to US-SC03)

Sample collection tasks follow [SH-10](../../shared.md#sh-10-tasks-and-to-do-list); reminders follow [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Scheduled task | Sales schedules a sample collection task on an order. A head of department's request to collect a sample again schedules one too. |
| Done by hand   | The sample collector marks the task done once the samples are collected.                                           |

Acceptance criteria:

- A collection task assigned to a sample collector appears on their personal schedule and in their to-do list.
- A reminder reaches the sample collector before the collection starts.
- A collection task created by a request to collect again shows the sample it is for.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Sample receiver](sample-receiver.md)
- [Shared technical features](../../shared.md)
