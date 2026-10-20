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

The work of a job is `_handle_<key with dots replaced by underscores>(self, item)` on `medilab.scheduled.job`. A feature module adds it by extending the model. A job that finds its own work, such as the samples whose retention ends soon or the stale document locks, also defines `_queue_<key with dots replaced by underscores>(self)`, which runs once as each run starts, before the run claims items, so the run also takes the items it queued. The handler returns nothing when the item is done, returns a `datetime` to defer the item without counting an attempt, raises `PermanentJobError` for a failure a retry cannot fix, and raises any other exception for a failure worth retrying.

### Claiming and retries

A batch claims due items with `FOR UPDATE SKIP LOCKED`, handles each one in a savepoint, and retries a failure with a delay that doubles up to the job's attempts. The item is then marked failed and an activity is created for the administrator. Abandoned claims, an item still running after the claim timeout, count an attempt. A second cron pass waits on Odoo's own scheduler lock.

Run now asks the cron worker to run the job and records who asked.

### Cleanup

The job `cleanup` runs daily and queues one item per kind and day, plus one per month of audit entries that is due. Each model it cleans names the records it removes in `_cleanup_domain(cutoff)`, and `CLEANUP_KINDS` in `constants/jobs.py` lists those models with the settings field of their retention period, 90 days by default:

| Kind            | Removed when                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------- |
| `job_items`     | Done or cancelled before the cutoff; failed items wait for a person                               |
| `job_runs`      | Ended before the cutoff, and named by no audit entry or archive file                              |
| `locks`         | Released or expired before the cutoff                                                             |
| `notifications` | MediLab's own notifications, read and posted before the cutoff; their pushes go with them          |
| `devices`       | Turned off before the cutoff                                                                      |

Audit entries are archived by calendar month, once the whole month is older than the audit retention period, which is empty by default and then keeps them for ever. `medilab.archive.file` writes the entries of the month, each with its changes, as gzip-compressed JSON lines to an attachment, reads the stored file back, and removes the entries only when its SHA-256 matches. A month is archived once: the period is unique per kind. The job removes no other model.

## Related documents

- [Shared technical features](../functional/shared.md): SH-09
- [Settings](settings.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
