# Onboarding crawler

Stories: US-AD32, US-AD33, US-AD34, US-AD35

## Goal

The Onboarding module reads public pages of trusted sources and turns them into staged records an administrator reviews, without ever reaching a site the developers did not ship, overloading a source, running anything a page contains or writing master data on its own.

## Design

### Models

| Model                              | Holds                                                                                              |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| `medilab.onboarding.source`        | A trusted source the developers ship: its adapter, host, start address, delay, page limit and whether it is turned on |
| `medilab.onboarding.organisation`  | An organisation a source lists, with its key at the source, name, tax ID and accreditation number  |
| `medilab.onboarding.run`           | One collection: its organisation, sectors, state, counts and log                                    |
| `medilab.onboarding.snapshot`      | One fetched document: its address, time, content type, checksum and the attachment with its bytes  |
| `medilab.onboarding.staged.record` | One proposed master data record: its kind, key at the source, values, edited values, action, match and state |

Runs and staged records are documents: they inherit `medilab.permission.mixin` and `medilab.audit.mixin` and ship their permissions in `data/permission_data.xml`, as [Module structure](../conventions/module_structure.md#permissions) says. A run names its staged records in `_audit_children`.

### Sources

Sources are chosen by the developers, not by the laboratory. Each source is a record in the module's `data/onboarding_source_data.xml`, with its adapter, host, start address, delay between requests (2 seconds by default), page limit per run (500 by default) and whether it is turned on. Adding, changing or turning off a source is a code change reviewed in a pull request, and reaches an installation when the module is upgraded.

The module ships two sources, turned on: the BoA organisation search, read by the `boa` adapter with a delay of 2 seconds, and the FDA Bacteriological Analytical Manual (BAM), read by the `fda_bam` adapter with a delay of 30 seconds. A source's delay is at least the `Crawl-delay` its `robots.txt` asks. The demo data turns every source off when it is installed and on every upgrade, so a demo never reaches a source.

The owner allows collecting from BoA. The BAM is in the public domain and serves food and cosmetics. Not shipped for now are the EPA's methods, whose reuse carries a non-commercial caveat; the TCVN standards at `tieuchuan.vsqi.gov.vn`, whose certificate chain does not verify, since the fetcher keeps verifying certificates; and the scopes of other laboratories.

- The source model is not a document: it has no permissions, no menu and no views, and no group, the administrator's included, gets an access rule on it. Code reads it with `sudo()`.
- Administrators see neither the sources nor their settings. A staged record shows only the address and time of the page it came from.
- A run reads every turned-on source: the organisation's own source for its scope, and every source whose adapter lists the run's sectors for them.

### Adapters

An adapter is a Python class registered under a key, such as `boa`, that knows the pages of one kind of source. A source names its adapter; a source of a new kind ships with its adapter. An adapter:

- lists the organisations of the source, as pages to fetch and a parser that yields organisations;
- gives the first pages of a run for an organisation and for sectors;
- parses a fetched document into staged values and further pages to fetch on the same host.

An adapter never makes a request itself. It only returns addresses, and the fetcher below fetches them, so every adapter follows the same safety rules.

The module ships these adapters:

| Adapter   | Reads                                                                                               | Stages                                                                                                                                                           |
| --------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `boa`     | The organisation search, page by page; an organisation's page; the PDFs of its accreditation scope. | Organisations; the certificate, from the organisation's page; the testing fields and methods of the list of accredited tests, each method under its certificate. |
| `fda_bam` | The chapter index of the Bacteriological Analytical Manual, for food and cosmetics.                 | The `Microbiology` field and one method per current chapter.                                                                                                     |

The `boa` adapter reads BoA's pages as follows:

- An organisation's key is the slug of its page, such as `phong-hoa-nghiem-xang-dau`, and its name is followed by its governing unit in parentheses when that is given and differs. BoA gives no tax ID. Every listed organisation is kept, whatever its status, and the next list page is the pager's `rel="next"` link.
- The certificate is staged from the organisation's page only, in Vietnamese: its code is the accreditation number, its issuing body `BoA` and its end of validity the page's "Ngày hiệu lực". Its start of validity stays empty for the administrator to fill: the published decision and scope leave its day blank, and staging the certificate from a second document as well would give it two checksums, so every run would supersede it.
- Both PDFs of the scope are fetched, since their addresses do not tell them apart. One whose text holds `LIST OF ACCREDITED TESTS` stages its testing fields and methods, in English; any other, such as the decision, stages nothing.
- A testing field's key is its Vietnamese name, such as `Hóa`, and its name the English one, such as `Chemical`; it has no code. A method belongs to the field of the last field header before its row.
- A method's key is its code: the standard body, the number without inner spaces, the version after `-` or `:`, and the reapproval year in parentheses when printed, such as `ASTM D525-12a (2019)`. Its name is the English test name of its row, else its code. A code listed in several rows is staged once, with its first row's name, under the certificate whose code the scope gives.

The `fda_bam` adapter reads one page, the chapter index, for food and for cosmetics alike, and lists no organisations. A chapter's key is `FDA BAM Ch. <number>`, such as `FDA BAM Ch. 4A`, and its name the chapter link's text. Every chapter is a method of the one field `Microbiology`, staged in English with the run's sector. Appendices and the archived chapters are skipped.

### Fetching

The fetcher is the only code that makes outbound requests. It uses `requests`, which Odoo already depends on.

- It fetches only `https` addresses on the source's host, verifies the certificate, follows no redirect by itself, and checks a redirect's target against the host before fetching it.
- It reads `robots.txt` of the host once per run and skips a disallowed path. A `robots.txt` that redirects off the host or more than five times disallows every path for the run; one that answers `4xx` or cannot be used, such as one that is not plain text, allows every path.
- It waits at least the source's delay between two requests of a source, across workers, by keeping the time of the last request on the source row, locked while it is read and written.
- It sends only `GET` requests with a `User-Agent` naming MediLab, no cookies kept between requests and no credentials.
- It stops reading a response after 10 MB and after a 30 second timeout, and accepts only HTML, PDF and JSON content types.
- It counts the pages of each source in a run against the source's page limit, and queues no more of that source's pages once the limit is reached.

The fetcher's tests show that a page on another host, a redirect off the host and a path `robots.txt` disallows are not fetched and are named in the run log; that two requests to a source are never closer than its delay; and that a run stops at the page limit, the size limit, the timeout and a refused content type.

### Parsing

A fetched document is data. HTML is parsed with `lxml` into a tree that is only read; no script, style or link in it is run or fetched. Text from PDF documents is extracted without running their actions; a PDF without text is skipped with a log line. Every staged value is plain text, trimmed, with control characters removed. Values keep the source's language in the language field of the staged record.

### Runs and the scheduled job

A run uses the job `onboarding.crawl` ([Scheduled jobs](scheduled-jobs.md)). Starting a run queues one item per first page of each source it reads, with the item key `<run id>:<address>` and the source in the payload, so an address is fetched once per run. The handler `_handle_onboarding_crawl` fetches the page, keeps the snapshot, has the adapter parse it, stages its records and queues the pages it links to. A network error or a `5xx` answer is retried, and while a source cannot be read its other pages wait for that page's first retry without spending an attempt; a `4xx` answer raises `PermanentJobError`. A run ends when it has no pending or running items left: `done` when none failed, `failed` otherwise, and its counts and log are written then. Cancelling a run cancels its pending items.

The job `onboarding.organisations` refreshes the organisations of each turned-on source, weekly by default, through the same fetcher. A refresh starts when the source has no refresh item pending or running and its last refresh began more than half the cron interval ago. When it starts, the organisations not seen since the previous refresh are archived, but only if that refresh had no failed page and saw at least one organisation.

Uninstalling the module turns the crons of both jobs off, deletes their items and the runs nothing refers to, and then the jobs left without runs, so Odoo removes their crons. A finished run carries the audit entry of its end, which only the cleanup job removes, so a job that has run stays, its cron off.

### Staging

The key of a staged record is its adapter's key for it at the source, such as a method's standard code within a certificate. A checksum of its values tells whether the source changed it:

- the same key and checksum as a staged record that is to review, accepted or rejected stages nothing;
- the same key with another checksum stages a new record, and an older one to review becomes `superseded` and passes its children, such as the methods of a certificate's scope, to the new one.

Matching an existing Laboratory record runs when a record is staged and again when its values are edited. Codes are compared after removing spaces and folding case and compatibility forms, such as full-width digits; names by trigram similarity, as a suggestion.

### Accepting

Accepting runs as the administrator, through the same `create` and `write` of the Laboratory models that their forms use, so their constraints, permissions and audit entries apply. It runs in the administrator's language, so Laboratory's messages come in that language; a name is written in the language of the staged record. A certificate with its scope goes through the import of [Import from certificate](../functional/laboratory_module/features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28), one import per testing field. Methods whose codes differ only in case, spaces and compatibility forms become one line, under the code of the method they match, if any. Each staged record is accepted in a savepoint with the records it needs, so a refusal leaves it and them to review and does not undo the others of a batch. The accepted record is kept on the staged record as its model and id.

Laboratory does not know about Onboarding. The module adds the origin to the forms of the master data it stages by extending their views with a button that opens the staged records of the record.

### Document types

| Document type | Actions            | Scopes |
| ------------- | ------------------ | ------ |
| Run           | read, create, edit | all    |
| Staged record | read, edit         | all    |

`create` makes a draft run; `edit` starts and cancels a run, refreshes the organisations, and edits, accepts, rejects and reopens staged records. Neither document has `delete`.

### Network

The cluster lets Odoo reach the hosts of the turned-on sources over HTTPS. No other outbound access is added for the module.

## Related documents

- [Onboarding overview](../functional/onboarding_module/overview.md)
- [Onboarding administrator](../functional/onboarding_module/features/admin.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Permissions](permissions.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/onboarding/onboarding.prisma)
