# Scheduled jobs

Stories: SH-09

## Goal

Recurring work runs by itself in batches, is safe to run twice, retries what fails a limited number of times, and shows administrators every job with its runs and their logs. Features queue their work on a job instead of running it inline, so a provider outage never loses a business action.

## Design

### Job, items and runs

- A **job** (`medilab.scheduled.job`) has a unique key, a name, and the Odoo cron that schedules it; the cron holds the schedule and the on or off switch. The job also holds its limits: the batch size, the attempts before an item fails, the claim timeout and the first retry delay.
- An **item** (`medilab.job.item`) is one unit of work queued for a job: a key unique within the job, the document it is about, a payload, and its status: `pending`, `running`, `done`, `failed` or `cancelled`. It records its attempts, the earliest time of the next attempt and the error of the last failed attempt.
- A **run** (`medilab.job.run`) records one pass of a job: when it started and ended, its result (`running`, `succeeded`, `partly_failed`, `failed`), its log with one line per item, how many items were done and how many failed an attempt, and who ran the job by hand. Odoo's cron progress shows how many items the current batch did and how many remain.

### Queuing work

A feature queues work with the key of the job and a key for the item:

```python
self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", f"payment_link:{link.id}", document=link, payload={...})
```

The same item key is queued once: an item that exists in any status is returned unchanged, and the unique constraint on the job and the item key settles a race between two transactions. New work takes a new key. Queuing runs with full rights, because features queue from any user's action.

### Handlers

The work of a job is a method named after its key on `medilab.scheduled.job`: `_handle_<key with dots replaced by underscores>(self, item)`, for example `_handle_payos_poll`. A feature module adds it by extending the model in a file named after it (`models/<concern>/scheduled_job.py`). The handler:

- returns nothing when the item is done;
- returns a `datetime` to defer the item to that time without counting an attempt, which is how a polling job waits for a provider;
- raises `PermanentJobError` for a failure a retry cannot fix, which marks the item failed at once;
- raises any other exception for a failure worth retrying.

A job whose handler is missing fails its run and leaves its items untouched.

### Declaring a job

A job and its cron are data of the feature module, both `noupdate="1"` so the schedule an administrator changes survives an upgrade:

```xml
<record id="cron_payos_poll" model="ir.cron">
    <field name="name">PayOS: check pending payment links</field>
    <field name="model_id" ref="laboratory.model_medilab_scheduled_job" />
    <field name="state">code</field>
    <field name="code">model._run_key("payos.poll")</field>
    <field name="interval_number">15</field>
    <field name="interval_type">minutes</field>
</record>
<record id="job_payos_poll" model="medilab.scheduled.job">
    <field name="key">payos.poll</field>
    <field name="name">PayOS status check</field>
    <field name="cron_id" ref="cron_payos_poll" />
</record>
```

The cron code string must not change, since the record is not updated on upgrade. A job created from Python without a cron gets a daily one.

### A pass

Odoo's cron scheduler starts a **pass** of the job and calls the cron code once per **batch**, up to ten times or ten seconds while the job reports items remaining, then reschedules it as soon as possible. Each batch:

1. Continues the run of the pass, or opens one. The batches of a pass share one run, found by the pass marker Odoo puts in the context; a run another pass left running is closed first with the note that it continued later. A new run takes the administrator who asked for a run by hand, when one did.
2. Releases abandoned claims: an item `running` longer than the job's claim timeout counts a failed attempt, then goes back to `pending` with the retry delay, or fails at the last attempt. An item that crashed the worker therefore ends failed instead of looping.
3. Claims up to the batch size of due items, `pending` with a next attempt at or before now, with one SQL update under `FOR UPDATE SKIP LOCKED`, so two workers never take the same item. This is the one place the module runs SQL itself, because the ORM cannot express `SKIP LOCKED`.
4. Handles each item in a savepoint, so a failing item rolls back only its own changes. Then it reports the item to Odoo's cron progress, which commits the batch so far.
5. Reports how many items remain due. None left closes the run; items left keep the run open for the next batch of the pass.

A run-level failure, such as the claim failing, marks the run `failed` with the error and does not raise, so Odoo's failure counter never deactivates the job's cron and hides it.

### Retries

An item whose handler raises counts an attempt and keeps its error. Below the job's attempts it goes back to `pending` with a delay that doubles each time: the retry delay, twice that, four times that. At the last attempt it is marked `failed` and `_notify_failed_item` is called. Until notifications exist, that hook writes the failure to the server log, and the Jobs screen shows the failed items of each job; the notifications feature turns the hook into a notification to administrators.

An administrator retries a failed item, which queues it again at once with its attempts kept, or cancels a pending or failed item.

### Running by hand and overlap

"Run now" needs the edit permission on the job and an active schedule. It writes who asked on the job and triggers the cron, so the pass runs in the cron worker within a minute; no run happens inside the web request, because handlers make external calls a rollback cannot undo. The requester is attributed to the next pass of the job, which may be a scheduled pass that starts first; the triggered pass that follows then finds nothing left to do.

Two passes of one job never overlap: the Odoo scheduler holds the cron's row lock for the whole pass, and a run by hand goes through the same scheduler. Correctness also rests on the claim: an item claimed by one batch is not pending for another.

### Permissions

Jobs ship with modules, so a job has the `read` and `edit` permissions (edit covers the schedule, the limits, running by hand), an item has `read` and `edit` (retry and cancel), and a run has `read`. Changing the schedule also writes the cron, which needs Odoo's settings group; the administrator role implies it.

## Related documents

- [Shared technical features](../functional/shared.md): SH-09
- [Settings](settings.md)
- [Permissions](permissions.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
