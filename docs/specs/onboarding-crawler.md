# Onboarding crawler

Stories: US-AD32, US-AD33, US-AD34, US-AD35, US-AD36

## Goal

The Onboarding module reads public pages of trusted sources and turns them into staged records an administrator reviews, without ever reaching a site the administrator did not approve, overloading a source, running anything a page contains or writing master data on its own.

## Design

### Models

| Model                              | Holds                                                                                              |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| `medilab.onboarding.source`        | A trusted source: its adapter, host, start address, delay, page limit and whether it is turned on |
| `medilab.onboarding.organisation`  | An organisation a source lists, with its key at the source, name, tax ID and accreditation number  |
| `medilab.onboarding.run`           | One collection: its source, organisation, sectors, state, counts and log                            |
| `medilab.onboarding.snapshot`      | One fetched document: its address, time, content type, checksum and the attachment with its bytes  |
| `medilab.onboarding.staged.record` | One proposed master data record: its kind, key at the source, values, edited values, action, match and state |

Runs and staged records are documents: they inherit `medilab.permission.mixin` and `medilab.audit.mixin` and ship their permissions in `data/permission_data.xml`, as [Module structure](../conventions/module_structure.md#permissions) says. A run names its staged records in `_audit_children`.

### Adapters

An adapter is a Python class registered under a key, such as `boa`, that knows the pages of one kind of source. A source names its adapter; adding a source of a new kind means shipping an adapter. An adapter:

- lists the organisations of the source, as pages to fetch and a parser that yields organisations;
- gives the first pages of a run for an organisation and for sectors;
- parses a fetched document into staged values and further pages to fetch on the same host.

An adapter never makes a request itself. It only returns addresses, and the fetcher below fetches them, so every adapter follows the same safety rules.

### Fetching

The fetcher is the only code that makes outbound requests. It uses `requests`, which Odoo already depends on.

- It fetches only `https` addresses on the source's host, verifies the certificate, follows no redirect by itself, and checks a redirect's target against the host before fetching it.
- It reads `robots.txt` of the host once per run and skips a disallowed path.
- It waits at least the source's delay between two requests of a source, across workers, by keeping the time of the last request on the source row, locked while it is read and written.
- It sends only `GET` requests with a `User-Agent` naming MediLab, no cookies kept between requests and no credentials.
- It stops reading a response after 10 MB and after a 30 second timeout, and accepts only HTML, PDF and JSON content types.
- It counts pages against the source's page limit and ends the run's queue when the limit is reached.

### Parsing

A fetched document is data. HTML is parsed with `lxml` into a tree that is only read; no script, style or link in it is run or fetched. Text from PDF documents is extracted without running their actions; a PDF without text is skipped with a log line. Every staged value is plain text, trimmed, with control characters removed. Values keep the source's language in the language field of the staged record.

### Runs and the scheduled job

A run uses the job `onboarding.crawl` ([Scheduled jobs](scheduled-jobs.md)). Starting a run queues one item per first page, with the item key `<run id>:<address>`, so an address is fetched once per run. The handler `_handle_onboarding_crawl` fetches the page, keeps the snapshot, has the adapter parse it, stages its records and queues the pages it links to. A network error or a `5xx` answer is retried; a `4xx` answer raises `PermanentJobError`. A run ends when its source has no pending or running items left: `done` when none failed, `failed` otherwise, and its counts and log are written then. Cancelling a run cancels its pending items.

The job `onboarding.organisations` refreshes the organisations of each turned-on source, weekly by default, through the same fetcher.

### Staging

The key of a staged record is its adapter's key for it at the source, such as a method's standard code within a certificate. A checksum of its values tells whether the source changed it:

- the same key and checksum as a staged record that is to review, accepted or rejected stages nothing;
- the same key with another checksum stages a new record, and an older one to review becomes `superseded`.

Matching an existing Laboratory record runs when a record is staged and again when its values are edited. Codes are compared after removing spaces and folding case; names with the trigram indexes of the master data tables, as a suggestion.

### Accepting

Accepting runs as the administrator, through the same `create` and `write` of the Laboratory models that their forms use, so their constraints, permissions and audit entries apply. A certificate with its scope goes through the import of [Import from certificate](../functional/laboratory_module/features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28). Each staged record is accepted in a savepoint with the records it needs, so a refusal leaves it and them to review and does not undo the others of a batch. The accepted record is kept on the staged record as its model and id.

Laboratory does not know about Onboarding. The module adds the origin to the forms of the master data it stages by extending their views with a button that opens the staged records of the record.

### Network

The cluster lets Odoo reach the hosts of the turned-on sources over HTTPS. No other outbound access is added for the module.

## Related documents

- [Onboarding overview](../functional/onboarding_module/overview.md)
- [Onboarding administrator](../functional/onboarding_module/features/admin.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Permissions](permissions.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/onboarding/onboarding.prisma)
