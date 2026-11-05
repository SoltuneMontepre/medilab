# Reports

Documents, diagrams and supporting material that belong to no other folder.

- [Capstone proposal](proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx): the registration of capstone project FA26SE294, which binds the project's scope
- [VILAS accreditation scopes](vilas/readme.md): the accredited tests of four VILAS laboratories from the BoA organisation search, as CSV, which ground the Laboratory catalog
- [Context diagram](context-diagram/readme.md): the DFD level 0 diagram of the subsystem, with its 13 entities, 70 flows and the deviations from the capstone proposal
- [Use case diagram](use-case-diagram/readme.md): the use cases of the Laboratory and E-commerce modules traced to their user stories, with the deviations from the proposal and the script that draws the diagram
- [Conceptual ERD](erd-diagram/readme.md): the business concepts of the Laboratory and E-commerce modules in Chen notation, as an overview and one diagram per area, with the findings on the conceptual model, the deviations from the proposal and the script that draws the diagrams
- [System activity diagram](activity-diagram/readme.md): the 17 business flows on one sheet, a frame per flow, with the system activity map, the joins between flows and the script that draws them
- [Activity diagram website](https://medilab-activity-diagrams.vercel.app): the system activity map with a page per flow, built by `activity-diagram/site/build.py` and deployed to Vercel

- [CloudBeaver initialization evidence](cloudbeaver-initialization.md): upstream lifecycle, comparison with the older implementation, regression coverage and production verification limits
- [CloudBeaver review](cloudbeaver-review.md): strict findings, real Kubernetes verification, production evidence gaps and rollout decision
- [CloudBeaver security and peer review](cloudbeaver-security-review.md): manual review findings, MD5 protocol/storage assessment and recovery safety boundaries
- [Local setup security review](local-setup-security-review.md): Sonar source-to-sink dispositions, private-state integrity fixes and security-owner gates
- [Cypress Tap and AI Skills](cypress-tap.md): verified capabilities, source pin, installation and validation requirements for local Cypress agent workflows
- [WF-03 test plan](wf-03-test-plan.md): testing assignment and scheduling: business rules, the scenario matrix and its coverage, concurrency design, confirmed defects and open decisions

## Related documents

- [Documentation index](../readme.md)
