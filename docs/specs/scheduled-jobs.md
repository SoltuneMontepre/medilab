# Scheduled jobs

Stories: SH-09

## Goal

Recurring work runs by itself in batches, is safe to run twice, retries what fails a limited number of times, and shows administrators every job with its runs and their logs. Features queue their work on a job instead of running it inline, so a provider outage never loses a business action.

## Design

### Job, items and runs

- A job (`medilab.scheduled.job`) has a unique key, a name, and the Odoo cron that schedules it. The cron holds the schedule and the on or off switch. The job also holds its limits: the batch size, the attempts before an item fails, the claim timeout and the first retry delay.
- An item (`medilab.job.item`) is one unit of work: a key unique within the job, the document it is about, a payload, and its status: `pending`, `running`, `done`, `failed` or `cancelled`. It records its attempts, the earliest time of the next attempt and the error of the last failed attempt.
- A run (`medilab.job.run`) records one pass of a job: when it started and ended, its result (`running`, `succeeded`, `partly_failed`, `failed`), its log with one line per item, how many items were done and how many failed an attempt, and who ran the job by hand.

### Queuing and handling

`queue(key, item_key, document=None, payload=None)` queues work once. The same item key is returned unchanged, and the unique constraint on the job and the item key settles a race.

The work of a job is `_handle_<key with dots replaced by underscores>(self, item)` on `medilab.scheduled.job`. A feature module adds it by extending the model. The handler returns nothing when the item is done, returns a `datetime` to defer the item without counting an attempt, raises `PermanentJobError` for a failure a retry cannot fix, and raises any other exception for a failure worth retrying.

### Claiming and retries

A batch claims due items with `FOR UPDATE SKIP LOCKED`, handles each one in a savepoint, and retries a failure with a delay that doubles up to the job's attempts. The item is then marked failed and an activity is created for the administrator. Abandoned claims, an item still running after the claim timeout, count an attempt. A second cron pass waits on Odoo's own scheduler lock.

Run now asks the cron worker to run the job and records who asked. The cleanup job and its archive files belong to a later feature.

## Related documents

- [Shared technical features](../functional/shared.md): SH-09
- [Settings](settings.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
