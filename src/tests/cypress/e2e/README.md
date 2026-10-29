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
        onboarding/master-data-staging/
        inventory/solution-preparation/
        theme/chatter-resize/
      *.cy.js
    support/
    fixtures/
```

- `flows/` holds the scenarios for WF-01 to WF-06 and SF-01 to SF-11. The table below maps each owning flow to its spec directory; one file suite can exercise both result-file work and file administration.
- `features/` holds browser scenarios whose feature has no owning business flow.
- `support/` holds shared authentication, record, action, refusal and form commands; `fixtures/` holds browser fixtures.
- `flows/<flow>/setup.js` builds the flow's starting records, such as an order taken to a given stage, so a spec runs again on the same database. `sol_demo` provides the catalog, customers, people and other records they read.
- Keep a directory's `.gitkeep` until its first real spec is added. Do not add empty `.cy.js` files or skipped placeholder tests.
- Existing flat specs keep their current paths. Inspect their cases when implementing a flow; reuse or move a matching case instead of adding a second copy.

## Business-flow specs

Paths below are relative to `cypress/e2e/`. The issue descriptions use flat paths; this layout groups those files by flow and preserves their spec basenames.

| Flow | Scope | Issue | Directory | Spec basename |
| --- | --- | --- | --- | --- |
| WF-01 | Order to approved test request | [#152](https://github.com/SoltuneMontepre/medilab/issues/152) | `flows/wf-01-order-to-test-request/` | `order-to-test-request.cy.js` |
| WF-02 | Sample reception and handover | [#153](https://github.com/SoltuneMontepre/medilab/issues/153) | `flows/wf-02-sample-reception/` | `sample-reception.cy.js` |
| WF-03 | Testing assignment and scheduling | [#154](https://github.com/SoltuneMontepre/medilab/issues/154) | `flows/wf-03-testing-scheduling/` | `testing-scheduling.cy.js`, `unhappy-paths.cy.js`, `notification-integrity.cy.js` |
| WF-04 | Result entry and approval | [#155](https://github.com/SoltuneMontepre/medilab/issues/155) | `flows/wf-04-result-approval/` | `result-approval.cy.js` |
| WF-05 | Outsourced testing | [#156](https://github.com/SoltuneMontepre/medilab/issues/156) | `flows/wf-05-outsourced-testing/` | `outsourced-testing.cy.js` |
| WF-06 | Report signing, release and delivery | [#157](https://github.com/SoltuneMontepre/medilab/issues/157) | `flows/wf-06-report-release/` | `report-release.cy.js` |
| WF-04, SF-11 | Result files and laboratory file administration | [#168](https://github.com/SoltuneMontepre/medilab/issues/168) | `flows/wf-07-laboratory-files/` | `laboratory-files.cy.js` |
| SF-01 | Invoicing and payment collection | [#158](https://github.com/SoltuneMontepre/medilab/issues/158) | `flows/sf-01-payment-collection/` | `payment-collection.cy.js` |
| SF-02 | Order cancellation | [#159](https://github.com/SoltuneMontepre/medilab/issues/159) | `flows/sf-02-order-cancellation/` | `order-cancellation.cy.js` |
| SF-03 | Change request on a signed document | [#160](https://github.com/SoltuneMontepre/medilab/issues/160) | `flows/sf-03-change-request/` | `change-request.cy.js` |
| SF-04 | Sample retention and disposal | [#161](https://github.com/SoltuneMontepre/medilab/issues/161) | `flows/sf-04-sample-disposal/` | `sample-disposal.cy.js` |
| SF-05 | Machine calibration and unavailability | [#162](https://github.com/SoltuneMontepre/medilab/issues/162) | `flows/sf-05-machine-unavailability/` | `machine-unavailability.cy.js` |
| SF-06 | Accreditation and registration renewal | [#163](https://github.com/SoltuneMontepre/medilab/issues/163) | `flows/sf-06-accreditation-renewal/` | `accreditation-renewal.cy.js` |
| SF-07 | Result dates and priority orders | [#164](https://github.com/SoltuneMontepre/medilab/issues/164) | `flows/sf-07-priority-order/` | `priority-order.cy.js` |
| SF-08 | Laboratory setup | [#165](https://github.com/SoltuneMontepre/medilab/issues/165) | `flows/sf-08-laboratory-setup/` | `laboratory-setup.cy.js` |
| SF-09 | Customer support and feedback | [#166](https://github.com/SoltuneMontepre/medilab/issues/166) | `flows/sf-09-support-feedback/` | `support-feedback.cy.js` |
| SF-10 | Machine queue and rescheduling | [#154](https://github.com/SoltuneMontepre/medilab/issues/154), [#164](https://github.com/SoltuneMontepre/medilab/issues/164) | `flows/wf-03-testing-scheduling/`, `flows/sf-07-priority-order/` | `testing-scheduling.cy.js`, `priority-order.cy.js` |

Start test titles with the issue's `TC-WF…`, `TC-SF…` or `TC-F…` ID. Map feature acceptance criteria to an existing path test when that path already checks them; add a separate test only for a criterion not covered by a path. Use the issue's explicit exclusions to keep another flow's paths with their owner.

## Feature specs

| Scope | Issue | Directory | Spec basename |
| --- | --- | --- | --- |
| Pick an organisation, start a run, review staged records and accept a certificate with its methods. | [#176](https://github.com/SoltuneMontepre/medilab/issues/176) | `features/onboarding/master-data-staging/` | `master-data-staging.cy.js` |
| Prepare a solution from scanned bottles; verify the resulting stock movements and container. | [#181](https://github.com/SoltuneMontepre/medilab/issues/181) | `features/inventory/solution-preparation/` | `solution-preparation.cy.js` |
| Resize and collapse the chatter that sits beside a form, and keep its width and state. | [#282](https://github.com/SoltuneMontepre/medilab/issues/282) | `features/theme/chatter-resize/` | `chatter-resize.cy.js` |

Onboarding and solution-preparation scenarios follow their approved feature documents and demo starting data. Reserving a directory does not settle the open requirements in those issues.

## Related issue ownership

The [open-issue query](https://github.com/SoltuneMontepre/medilab/issues?q=is%3Aissue+state%3Aopen+browser+tests) also includes shared tooling and feature or infrastructure issues. Keep their browser assertions with the owning flow instead of duplicating a complete flow under each issue.

| Issue | Browser-test location | Scope boundary |
| --- | --- | --- |
| [#151](https://github.com/SoltuneMontepre/medilab/issues/151) | `../support/`; `browser_helpers.cy.js`, `demo_roles.cy.js`, `login.cy.js` | Shared commands, authentication and helper checks. |
| [#170](https://github.com/SoltuneMontepre/medilab/issues/170) | `flows/wf-07-laboratory-files/` | File/version history, downloads, conflicts and restore; the remaining large-file, deployed-concurrency and bucket-policy evidence stays with its staging and infrastructure checks. |
| [#171](https://github.com/SoltuneMontepre/medilab/issues/171) | `flows/wf-07-laboratory-files/` | Online editing and saving, including WF-04-A8; callback HTTP, transaction and concurrency tests remain in the module suite. |
| [#179](https://github.com/SoltuneMontepre/medilab/issues/179) | `flows/sf-07-priority-order/` | Changing and checking a due date, including SF-07-A3. |
| [#184](https://github.com/SoltuneMontepre/medilab/issues/184) | `flows/wf-04-result-approval/` | Web verification that a mobile-signed result awaits the head of department; native screens and the Android emulator path belong to the mobile app suite. |
| [#203](https://github.com/SoltuneMontepre/medilab/issues/203) | `flows/wf-07-laboratory-files/` | Real Document Server browser editing and service-down behavior; deployment, network, persistence, monitoring and licence gates keep their infrastructure ownership. |
| [#220](https://github.com/SoltuneMontepre/medilab/issues/220) | `login.cy.js` | Reproduce and fix the existing wrong-password browser case. The other failures listed in the issue are Odoo module tests. |
| [#230](https://github.com/SoltuneMontepre/medilab/issues/230) | `flows/wf-07-laboratory-files/` | Authenticated editor-page navigation, return after login, refusal messages, browser security and real-editor interaction. |

Use the pinned running Document Server for acceptance criteria that require the real editor. A browser fixture or a passing Cypress case does not replace the native, API, infrastructure or staging evidence an issue requires.

## Related documents

- [Testing conventions](../../../../docs/conventions/testing.md)
- [Business flows](../../../../docs/functional/business-flows.md)
