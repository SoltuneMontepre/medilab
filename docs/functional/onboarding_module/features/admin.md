# Features of: Administrator

The administrator fills the Laboratory master data from trusted public sources: picks the laboratory's organisation and sectors, runs collections and reviews what they stage. The sources themselves are chosen and configured by the developers and shipped with the module; administrators do not see or change them, as [Onboarding crawler](../../../specs/onboarding-crawler.md#sources) says. The tables are drawn in [onboarding.prisma](../../../infrastructure/database/onboarding/onboarding.prisma).

## I. User stories

- **US-AD32** As an administrator, I want to pick my laboratory from the organisations a source lists, with the system suggesting it from the company's details, so that the laboratory's own accreditation scope is collected without typing it.
- **US-AD33** As an administrator, I want to choose the sectors the laboratory tests in, such as food, and have the system collect the testing methods, parameters and sample types the sources list for them, so that the catalog starts from what such laboratories test.
- **US-AD34** As an administrator, I want to review the collected records, edit them, and accept or reject them, so that only checked data becomes master data.
- **US-AD35** As an administrator, I want to see each collection run with what it fetched and staged, and where each accepted record came from, so that collected master data can be traced to its source.

## II. Feature details

### 1. Collecting (US-AD32, US-AD33, US-AD35)

| Rule            | Description                                                                                                                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Organisations   | A [scheduled job](../../shared.md#sh-09-scheduled-tasks) refreshes the organisations the sources list, weekly by default, and the administrator can refresh them by hand. Picking an organisation searches this list, never a source's site. |
| Suggestion      | Picking an organisation suggests first the one whose tax ID is the company's, then those whose names are closest to the company's name. The administrator can pick any listed organisation or none. |
| Sectors         | The administrator picks one or more of the sectors the system serves: food, cosmetics, pharmaceuticals and environment.                                                                          |
| What a run reads | A run has an organisation, sectors or both. For the organisation, it stages its accreditation certificates with their scope. For the sectors, it stages what the sources list for them. |
| Background      | A run works through a scheduled job, one item per page, so the administrator can leave the screen. The administrator who started it is notified when it ends.                                      |
| One at a time   | At most one run is running. Starting another is refused until the first ends.                                                                                                                       |
| Snapshot        | Every document a run fetches is kept unchanged with its address, the time and its checksum. Every staged record names the snapshot it came from.                                                  |
| Seen before     | A record a source gives with the same values as a staged record still to review, accepted or rejected is not staged again. With other values, it is staged again as an update, and an older one still to review is superseded. |
| Run report      | A run shows how many pages it fetched and skipped, the records it staged per kind and the pages that failed.                                                                                       |
| Cancelling      | The administrator can cancel a running run. It fetches nothing more, and what it already staged stays to review.                                                                                   |

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> running: started
    running --> done: every page handled
    running --> failed: a page failed every attempt
    running --> cancelled: cancelled by the administrator
    done --> [*]
    failed --> [*]
    cancelled --> [*]
```

Acceptance criteria:

- With the company's tax ID equal to a listed organisation's, that organisation is the first suggestion.
- A run for the food sector stages only what the sources list for food.
- Running the same collection twice on unchanged sources stages nothing the second time.
- When the source changes a method's title, the next run stages an update, and the earlier record of that method still to review becomes superseded.
- A page that fails every attempt ends the run as failed, names the page in the log, and keeps what the run staged.
- A cancelled run fetches no more pages and keeps what it staged.
- Starting a second run while one is running is refused with a message.
- Each staged record shows the address and time of the page it came from.

### 2. Reviewing staged records (US-AD34, US-AD35)

| Rule              | Description                                                                                                                                                                                                            |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Proposed action   | A staged record proposes to create a record when it matches none, to link an existing record that it matches with the same values, or to update a record it matches with other values.                                  |
| Matching          | A certificate matches by its number and a testing method by its standard code, both ignoring case and spaces. A testing field, a sample type and a test parameter match by name in the source's language; a name match is a suggestion the administrator confirms. |
| Editing           | Before accepting, the administrator can edit the values and the match. The values the source gave are kept unchanged next to the edited ones.                                                                           |
| Accepting         | Accepting creates, links or updates the Laboratory record by the rules of the [Catalog](../../laboratory_module/features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28). When Laboratory refuses it, such as for a duplicate code, the record stays to review with the message. |
| Needed first      | Accepting a record also accepts the staged records it needs: a way of testing its parameter and method, a certificate the methods of its scope, a method its testing field. What Laboratory requires and the source does not give, such as the department of an in-house way of testing, is asked when accepting. |
| Updates           | Accepting an update shows the current and the new values side by side and changes only the fields that differ. It does not restore an archived record.                                                                  |
| Many at once      | The administrator can accept or reject many staged records at once. The result lists each one that was refused with its message; those stay to review.                                                               |
| Rejecting         | A rejected record has an optional reason. Later runs do not stage it again while the source keeps the same values. The administrator can reopen it.                                                                    |
| Nothing automatic | No staged record becomes master data without an administrator accepting it.                                                                                                                                          |
| Origin            | A Laboratory record created, linked or updated by accepting shows its origin: the staged records with the address and time of the page each came from.                                                                    |
| Permissions       | Reading runs and staged records, starting runs, and accepting and rejecting are permissions the administrator holds and can give to other roles and people. Accepting also needs the permission to create or edit the master data it changes. No permission shows the sources. |

```mermaid
stateDiagram-v2
    [*] --> to_review: staged by a run
    to_review --> accepted: accepted
    to_review --> rejected: rejected
    to_review --> superseded: a later run staged other values
    rejected --> to_review: reopened
    accepted --> [*]
    superseded --> [*]
```

Acceptance criteria:

- A staged method whose standard code exists, written with other case or spaces, proposes to link that method.
- A staged certificate accepted with 30 methods, 5 of them already existing, creates 25 methods, links all 30 and leaves the 5 unchanged.
- Accepting a way of testing whose parameter and method are staged accepts them first.
- Accepting an in-house way of testing without a department asks for one, and nothing is saved until it is given.
- Accepting a record that Laboratory refuses leaves it to review with the message, and accepts nothing else for it.
- Accepting 20 records at once of which 2 are refused accepts 18 and lists the 2 with their messages.
- Accepting an update changes only the fields that differ.
- Editing a staged value keeps the source's value, and the accepted record has the edited one.
- A rejected record is not staged again while its source is unchanged, and can be reopened.
- A testing method created by accepting shows its origin with the address of the page it came from.
- No menu, form or list shows the sources to an administrator, and the API refuses to read them.
- Someone without the permission to accept staged records does not see the Accept button, and the API refuses it.

## III. Related documents

- [Onboarding overview](../overview.md)
- [Onboarding crawler](../../../specs/onboarding-crawler.md)
- [Laboratory administrator](../../laboratory_module/features/admin.md)
- [Shared technical features](../../shared.md)
