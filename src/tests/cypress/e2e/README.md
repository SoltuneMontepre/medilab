# Browser test layout

Keep each business-flow path in one owning flow. Each test creates the records it starts from with its flow's `setup.js`, through the model methods each actor's screen calls, and uses the shared commands rather than replaying another flow's screens.

## Directories

```text
src/tests/
  cypress.config.js
  cypress/
    e2e/
      flows/
        wf-01-order-to-test-request/
        wf-02-sample-reception/
        wf-03-testing-scheduling/
        wf-04-result-approval/
        wf-05-outsourced-testing/
        wf-06-report-release/
        wf-07-laboratory-files/
        sf-01-payment-collection/
        sf-02-order-cancellation/
        sf-03-change-request/
        sf-04-sample-disposal/
        sf-05-machine-unavailability/
        sf-06-accreditation-renewal/
        sf-07-priority-order/
        sf-08-laboratory-setup/
        sf-09-support-feedback/
      features/
        catalog/regulation-limits/
        catalog/sample-type-applicability/
        laboratory/accreditation-scope/
        laboratory/backup-signers/
        laboratory/overtime/
        onboarding/master-data-staging/
        inventory/solution-preparation/
        theme/chatter-resize/
        theme/navbar-more-menu/
        laboratory/unlinked-users/
        laboratory/shared-intervals/
        ecommerce/mandatory-notices/
        laboratory/department-plan/
        laboratory/machine-conditions/
        laboratory/interruptions/
        ecommerce/portal-language/
        ecommerce/portal-navigation/
        ecommerce/uninstall-warning/
        mobile/phone-revocation/
        mobile/tasks/
        laboratory/document-locking/
        laboratory/audit-trail/
        laboratory/scheduled-jobs/
      *.cy.js
    support/
    fixtures/
```

- `flows/` holds the scenarios for WF-01 to WF-06 and SF-01 to SF-11. The table below maps each owning flow to its spec directory; one file suite can exercise both result-file work and file administration.
- `features/` holds browser scenarios whose feature has no owning business flow, such as a feature that every flow uses.
- The tests of a feature's acceptance criteria live in the directory of the flow that owns the feature: its Workflow in the [feature list](../../../../docs/reports/feature-list/readme.md). A flow keeps its path tests in its first spec below and its features' tests in specs named after those features.
- `support/` holds shared authentication, record, action, refusal and form commands; `fixtures/` holds browser fixtures.
- `flows/<flow>/setup.js` builds the flow's starting records, such as an order taken to a given stage, so a spec runs again on the same database. `sol_demo` provides the catalog, customers, people and other records they read.
- Keep a directory's `.gitkeep` until its first real spec is added. Do not add empty `.cy.js` files or skipped placeholder tests.
- Existing flat specs keep their current paths. Inspect their cases when implementing a flow; reuse or move a matching case instead of adding a second copy.

## Business-flow specs

Paths below are relative to `cypress/e2e/`. The issue descriptions use flat paths; this layout groups those files by flow and preserves their spec basenames.

| Flow | Scope | Issue | Directory | Spec basename |
| --- | --- | --- | --- | --- |
| WF-01 | Order to confirmed test request | [#152](https://github.com/SoltuneMontepre/medilab/issues/152) | `flows/wf-01-order-to-test-request/` | `order-to-test-request.cy.js`, `cart-and-claiming.cy.js`, `quotation.cy.js`, `payment-and-confirmation.cy.js` |
| WF-02 | Sample reception and handover | [#153](https://github.com/SoltuneMontepre/medilab/issues/153) | `flows/wf-02-sample-reception/` | `sample-reception.cy.js` |
| WF-03 | Testing assignment and scheduling | [#154](https://github.com/SoltuneMontepre/medilab/issues/154), [#315](https://github.com/SoltuneMontepre/medilab/issues/315) | `flows/wf-03-testing-scheduling/` | `testing-scheduling.cy.js`, `unhappy-paths.cy.js`, `reassignment-reasons.cy.js`, `reassignment-handover.cy.js`, `sample-test-cancellation.cy.js`, `booking-rescheduling.cy.js`, `plan-revision.cy.js`, `notification-integrity.cy.js`, `booking-adjustments.cy.js` |
| WF-04 | Result entry and approval | [#155](https://github.com/SoltuneMontepre/medilab/issues/155) | `flows/wf-04-result-approval/` | `result-approval.cy.js` |
| WF-05 | Outsourced testing | [#156](https://github.com/SoltuneMontepre/medilab/issues/156) | `flows/wf-05-outsourced-testing/` | `outsourced-testing.cy.js` |
| WF-06 | Report signing, release and delivery | [#157](https://github.com/SoltuneMontepre/medilab/issues/157), [#431](https://github.com/SoltuneMontepre/medilab/issues/431), [#432](https://github.com/SoltuneMontepre/medilab/issues/432) | `flows/wf-06-report-release/` | `report-release.cy.js`, `report-preparation.cy.js` |
| WF-04, SF-11 | Result files and laboratory file administration: the back-office screens that browse, download, sign and administer folders, members, versions, locks and devices, and the device API calls a Medilab Sync computer makes against them, uploads with real bytes included. Medilab Sync's own screens and saves in the real editor are not exercised here, lock expiry is simulated, and TC-F53-03 leaves the folder of a hidden sample uncovered. | [#168](https://github.com/SoltuneMontepre/medilab/issues/168) | `flows/wf-07-laboratory-files/` | `laboratory-files.cy.js`, `laboratory-file-versions.cy.js` |
| SF-01 | Invoicing and payment collection | [#158](https://github.com/SoltuneMontepre/medilab/issues/158) | `flows/sf-01-payment-collection/` | `payment-collection.cy.js` |
| SF-02 | Order cancellation | [#159](https://github.com/SoltuneMontepre/medilab/issues/159) | `flows/sf-02-order-cancellation/` | `order-cancellation.cy.js` |
| SF-03 | Change request on a signed document | [#160](https://github.com/SoltuneMontepre/medilab/issues/160) | `flows/sf-03-change-request/` | `change-request.cy.js` |
| SF-04 | Sample retention, return and disposal | [#161](https://github.com/SoltuneMontepre/medilab/issues/161) | `flows/sf-04-sample-disposal/` | `sample-disposal.cy.js` |
| SF-05 | Machine calibration and unavailability | [#162](https://github.com/SoltuneMontepre/medilab/issues/162) | `flows/sf-05-machine-unavailability/` | `machine-unavailability.cy.js` |
| SF-06 | Accreditation and registration renewal | [#163](https://github.com/SoltuneMontepre/medilab/issues/163) | `flows/sf-06-accreditation-renewal/` | `accreditation-renewal.cy.js`, `accreditation-and-registrations.cy.js` |
| SF-07 | Result dates and priority orders | [#164](https://github.com/SoltuneMontepre/medilab/issues/164) | `flows/sf-07-priority-order/` | `priority-order.cy.js` |
| SF-08 | Laboratory setup | [#165](https://github.com/SoltuneMontepre/medilab/issues/165) | `flows/sf-08-laboratory-setup/` | `laboratory-setup.cy.js`, `catalog-and-prices.cy.js`, `parameters-and-chemicals.cy.js`, `people-and-approval-chains.cy.js`, `settings.cy.js` |
| SF-09 | Customer support and feedback | [#166](https://github.com/SoltuneMontepre/medilab/issues/166) | `flows/sf-09-support-feedback/` | `support-feedback.cy.js`, `customer-accounts.cy.js` |
| SF-10 | Scheduling plan and revisions | [#154](https://github.com/SoltuneMontepre/medilab/issues/154), [#164](https://github.com/SoltuneMontepre/medilab/issues/164) | `flows/wf-03-testing-scheduling/`, `flows/sf-07-priority-order/` | `testing-scheduling.cy.js`, `sample-test-cancellation.cy.js`, `booking-rescheduling.cy.js`, `priority-order.cy.js` |

Start test titles with the issue's `TC-WF…`, `TC-SF…` or `TC-F…` ID. When a path test checks the whole of a feature acceptance criterion, its title carries the path ID, then the criterion's ID, such as `TC-SF08-E2 TC-F01-03 refuses archiving…`, and no other test checks that criterion; add a separate test only for a criterion no path test checks whole. Use the issue's explicit exclusions to keep another flow's paths with their owner.

### WF-03 and SF-10 path coverage

A title carries a path ID from [Business flows](../../../../docs/functional/business-flows.md) only when its test checks part of that path's approved behavior. `partial` marks coverage of part of the path. The current WF-03 baseline requires the head to approve a feasible proposed booking, after which the tester receives an approval notice and a reminder. These steps are outside the coverage below. The [WF-03 test plan](../../../../docs/reports/wf-03-test-plan.md#125-browser-test-traceability) maps every path to its coverage and records the renamed test titles.

| Title starts with | Spec | What the browser proves |
| --- | --- | --- |
| `TC-WF03-M partial` | `testing-scheduling.cy.js` | The head assigns the test, which notifies the tester. The tester sees the proposed booking but cannot reserve it; the head approves it with Approve Booking, which books the recommended machine and slot, notifies the tester and shows in Machine Schedule, the calendar and the task's planned times. |
| `TC-WF03-A1 partial` | `testing-scheduling.cy.js` | A tester claims an unassigned task of their department and finds it in My Tasks; claiming notifies nobody. |
| `TC-WF03-A2 partial` | `testing-scheduling.cy.js` | Approve Booking reserves the machine and the step room together; the room events show in the Room Bookings tab and the tester's calendar, and cannot be removed apart from the machine booking. |
| `TC-WF03-E1 partial` | `testing-scheduling.cy.js`, `reassignment-handover.cy.js` | The head moves a task to another person, then another department, with a reason. The receiving person is told of the task and of the booking the head approves, finds the task in My Tasks and the booking in Machine Schedule; the previous person finds neither. |
| `TC-WF03-E2 partial` | `unhappy-paths.cy.js` | A test no machine can finish before its due date shows the outsourcing warning, goes to the head's review, has no Approve Booking button, refuses approval over RPC and creates no booking or event. |
| `TC-SF10-A2 partial` | `testing-scheduling.cy.js`, `booking-rescheduling.cy.js` | The tester cancels a booking. The head moves a booking to a free slot through the form and by dragging it in the calendar, and every reservation of the booking moves by the same time; a drop onto another booking's slot is refused; the head cancels a booking and the test stays assigned and open to Schedule. |
| `TC-SF10-A3 partial` | `sample-test-cancellation.cy.js` | The head cancels a booked test with a reason, which cancels its task, booking and events and leaves the sample's other test and another booked test unchanged; a tester has no Cancel Test button and RPC refuses it. |

WF-03-A3 and SF-10-A1, A4 and E1 through E4 depend on the features listed in the test plan. SF-10-A5 covers early machine release and is outside [#154](https://github.com/SoltuneMontepre/medilab/issues/154).

Issue [#318](https://github.com/SoltuneMontepre/medilab/issues/318) tracks `TC-WF03-A2 partial`, formerly `TC-WF03-A5`. It requires a passing rerun on the same database, unchanged recommendations in the other WF-03 tests and a green `e2e` job.

## Feature specs

| Scope | Issue | Directory | Spec basename |
| --- | --- | --- | --- |
| Configure the unit, detection limits and default of a way of testing on a sample type; a quotation tests the parameter on that type and refuses a sibling type the parameter is not configured for. | [#409](https://github.com/SoltuneMontepre/medilab/issues/409) | `features/catalog/sample-type-applicability/` | `sample-type-applicability.cy.js` |
| See that a regulation's covered sample type has no limit of its own, add its row from the catalog and save a limit; a duplicate limit and an expired regulation are refused. | [#410](https://github.com/SoltuneMontepre/medilab/issues/410) | `features/catalog/regulation-limits/` | `regulation-limits.cy.js` |
| Import scope lines into a certificate with their parameters and sample types; a sample test is accredited only when one line covers its method, parameter and sample type or an ancestor, and never when subcontracted. | [#412](https://github.com/SoltuneMontepre/medilab/issues/412) | `features/laboratory/accreditation-scope/` | `accreditation-scope.cy.js` |
| Pick an organisation, start a run, review staged records and accept a certificate with its methods. | [#176](https://github.com/SoltuneMontepre/medilab/issues/176) | `features/onboarding/master-data-staging/` | `master-data-staging.cy.js` |
| Prepare a solution from scanned bottles; verify the resulting stock movements and container. | [#181](https://github.com/SoltuneMontepre/medilab/issues/181) | `features/inventory/solution-preparation/` | `solution-preparation.cy.js` |
| Resize and collapse the chatter that sits beside a form, and keep its width and state. | [#282](https://github.com/SoltuneMontepre/medilab/issues/282) | `features/theme/chatter-resize/` | `chatter-resize.cy.js` |
| Move the menu bar sections that do not fit a narrow window into the More menu, in every app. | [#393](https://github.com/SoltuneMontepre/medilab/issues/393) | `features/theme/navbar-more-menu/` | `navbar-more-menu.cy.js` |
| Move a booking into another sample's machine interval of the same method, which books its room once, and refuse a sample once the interval is full. | [#420](https://github.com/SoltuneMontepre/medilab/issues/420) | `features/laboratory/shared-intervals/` | `shared-intervals.cy.js` |
| See that a booking whose end passed still holds its machine and puts the next booking on it at risk, which stays where it is. | [#424](https://github.com/SoltuneMontepre/medilab/issues/424) | `features/laboratory/machine-conditions/` | `machine-conditions.cy.js` |
| Assess the interrupted result a machine failure keeps as usable, needing a retest or needing more sample, as the head of the department that tested it; the tester cannot. | [#425](https://github.com/SoltuneMontepre/medilab/issues/425) | `features/laboratory/interruptions/` | `interruptions.cy.js` |
| Link an internal user that no person links to, and refuse creating one outside a person. | [#438](https://github.com/SoltuneMontepre/medilab/issues/438) | `features/laboratory/unlinked-users/` | `unlinked-users.cy.js` |
| Give a backup the head of department's role until a date, who approves a result or sends one at a lower level in their own name. | [#430](https://github.com/SoltuneMontepre/medilab/issues/430) | `features/laboratory/backup-signers/` | `backup-signers.cy.js` |
| Keep a mandatory notice in the portal of a customer whose email bounced, mark it seen when opened, and show it to no other customer. | [#436](https://github.com/SoltuneMontepre/medilab/issues/436) | `features/ecommerce/mandatory-notices/` | `mandatory-notices.cy.js` |
| Open the testing statistics of a period: a head of department sees their department; the Lab Head compares departments and a department filter gives what its head sees. | [#440](https://github.com/SoltuneMontepre/medilab/issues/440) | `features/laboratory/testing-statistics/` | `testing-statistics.cy.js` |
| Offer the head only people authorized for a testing task's parameter and refuse another, assign an authorized tester, and let only the lab head authorize a person. | [#421](https://github.com/SoltuneMontepre/medilab/issues/421) | `features/laboratory/parameter-authorization/` | `parameter-authorization.cy.js` |
| Approve the booking the department's plan proposes, which reserves the machine and the calendar and notifies the tester, and mark a test urgent with a reason. | [#422](https://github.com/SoltuneMontepre/medilab/issues/422) | `features/laboratory/department-plan/` | `department-plan.cy.js` |
| Switch the portal language from the header and the account page, as a customer and as a visitor. | [#451](https://github.com/SoltuneMontepre/medilab/issues/451) | `features/ecommerce/portal-language/` | `portal-language.cy.js` |
| Reach the catalog, My orders, Support and the account from the portal header, as a customer and as a visitor, and filter My orders. | [#452](https://github.com/SoltuneMontepre/medilab/issues/452), [#499](https://github.com/SoltuneMontepre/medilab/issues/499) | `features/ecommerce/portal-navigation/` | `portal-navigation.cy.js` |
| Warn before uninstalling E-commerce that test requests keep their order's number, and not when Laboratory leaves with it. | [#439](https://github.com/SoltuneMontepre/medilab/issues/439) | `features/ecommerce/uninstall-warning/` | `uninstall-warning.cy.js` |
| Revoke a phone signed in on Medilab Mobile from the back office; its key is refused at its next call and its push token is off. | [#514](https://github.com/SoltuneMontepre/medilab/issues/514) | `features/mobile/phone-revocation/` | `phone-revocation.cy.js` |
| Claim a task from the queue on the phone; the web shows it claimed, and a second claim is told it is already claimed. | [#516](https://github.com/SoltuneMontepre/medilab/issues/516) | `features/mobile/tasks/` | `tasks.cy.js` |
| See who holds the lock of a document another user is editing, and keep a signed document read-only for everyone, administrators included. | [#157](https://github.com/SoltuneMontepre/medilab/issues/157) | `features/laboratory/document-locking/` | `document-locking.cy.js` |
| Record who changed a price, when, and its old and new value; include a request's samples and sample tests in its history; let nobody change or delete an audit entry. | [#157](https://github.com/SoltuneMontepre/medilab/issues/157) | `features/laboratory/audit-trail/` | `audit-trail.cy.js` |
| List every scheduled job with its runs and run one by hand, and keep old audit entries in a checked archive file once the cleanup removes them. | [#157](https://github.com/SoltuneMontepre/medilab/issues/157) | `features/laboratory/scheduled-jobs/` | `scheduled-jobs.cy.js` |
| Record planned OverTime for a tester as their head of department; the tester is booked in it only once it is recorded, and moving the booking leaves it. | [#426](https://github.com/SoltuneMontepre/medilab/issues/426) | `features/laboratory/overtime/` | `overtime.cy.js` |

Solution-preparation scenarios follow their approved feature document and demo starting data. Reserving a directory does not settle the open requirements in that issue.

## Related issue ownership

The [open-issue query](https://github.com/SoltuneMontepre/medilab/issues?q=is%3Aissue+state%3Aopen+browser+tests) also includes shared tooling and feature or infrastructure issues. Keep their browser assertions with the owning flow instead of duplicating a complete flow under each issue.

| Issue | Browser-test location | Scope boundary |
| --- | --- | --- |
| [#151](https://github.com/SoltuneMontepre/medilab/issues/151) | `../support/`; `browser_helpers.cy.js`, `demo_roles.cy.js`, `login.cy.js` | Shared commands, authentication and helper checks. |
| [#170](https://github.com/SoltuneMontepre/medilab/issues/170) | `flows/wf-07-laboratory-files/` | File/version history, downloads, conflicts and restore; the remaining large-file, deployed-concurrency and bucket-policy evidence stays with its staging and infrastructure checks. |
| [#171](https://github.com/SoltuneMontepre/medilab/issues/171) | `flows/wf-07-laboratory-files/` | Online editing and saving, including WF-04-A8; callback HTTP, transaction and concurrency tests remain in the module suite. |
| [#179](https://github.com/SoltuneMontepre/medilab/issues/179) | `flows/sf-07-priority-order/` | Changing and checking a due date, including SF-07-A3. |
| [#184](https://github.com/SoltuneMontepre/medilab/issues/184), [#518](https://github.com/SoltuneMontepre/medilab/issues/518) | `flows/wf-04-result-approval/`; `mobile-bench.cy.js` | Web verification that a mobile-signed result awaits the head of department with the tester's signature; native screens and the Android emulator path belong to the mobile app's Jest tests and Maestro flows. |
| [#203](https://github.com/SoltuneMontepre/medilab/issues/203) | `flows/wf-07-laboratory-files/` | Real Document Server browser editing and service-down behavior; deployment, network, persistence, monitoring and licence gates keep their infrastructure ownership. |
| [#220](https://github.com/SoltuneMontepre/medilab/issues/220) | `login.cy.js` | Reproduce and fix the existing wrong-password browser case. The other failures listed in the issue are Odoo module tests. |
| [#431](https://github.com/SoltuneMontepre/medilab/issues/431) | `flows/wf-06-report-release/` | Editing, preparing and reviewing a report's PDF, WF-06-A5 and WF-06-E4, and the template versions an administrator sees. Preparing runs against a running editing service; without one, only the outage path runs. Template lifecycle, binding and callback rules remain in the module suite. |
| [#432](https://github.com/SoltuneMontepre/medilab/issues/432) | `flows/wf-06-report-release/` | WF-06-E1: a report pending digital signing stays unissued, a retry issues its reviewed PDF once, and an issued report stays current while its replacement waits. Viettel Sign outages, withdrawn approvals, stale PDFs and linked result corrections remain in the module suite. |
| [#230](https://github.com/SoltuneMontepre/medilab/issues/230) | `flows/wf-07-laboratory-files/` | Authenticated editor-page navigation, return after login, refusal messages, browser security and real-editor interaction. |

Use the pinned running Document Server for acceptance criteria that require the real editor. A browser fixture or a passing Cypress case does not replace the native, API, infrastructure or staging evidence an issue requires.

## Related documents

- [Testing conventions](../../../../docs/conventions/testing.md)
- [Business flows](../../../../docs/functional/business-flows.md)
