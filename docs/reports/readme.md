# Reports

Documents, diagrams and supporting material that belong to no other folder.

- [Capstone proposal](proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx): the registration of capstone project FA26SE294, which binds the project's scope
- [VILAS accreditation scopes](vilas/readme.md): the accredited tests of four VILAS laboratories from the BoA organisation search, as CSV, which ground the Laboratory catalog
- [Context diagram](context-diagram/readme.md): the DFD level 0 diagram of the subsystem, with its 13 entities, 70 flows and the deviations from the capstone proposal
- [Use case diagram](use-case-diagram/readme.md): the use cases of the Laboratory and E-commerce modules traced to their user stories, with the deviations from the proposal and the script that draws the diagram
- [Conceptual ERD](erd-diagram/readme.md): the business concepts of the Laboratory and E-commerce modules in Chen notation, as an overview and one diagram per area, with the findings on the conceptual model, the deviations from the proposal and the script that draws the diagrams
- [Activity diagrams](activity-diagram/readme.md): the system activity map and an activity diagram per business flow, with the script that builds their website, PDF and zip
- [Activity diagram website](https://soltunemontepre.github.io/medilab/): the system activity map with a page per flow, built by `activity-diagram/site/build.py` and published with GitHub Pages
- [Payment model choices](payment-model/payment-options.drawio): the three ways of recording an advance and the chosen one, what a payment waiting for the accountant blocks, and the states of a customer allowed to pay later, with a picture of each page
- [Review 2 commitment (BM04)](BM04_hoang/SWP490_GFA26SE153_R2_Commitment_v1.1.pdf): the features, workflows, demo scenarios and tests the team commits to for Defense 1.1, as version 1.1, version 1.0 and their comparison, with the workflow guideline it follows

- [CloudBeaver initialization evidence](cloudbeaver-initialization.md): upstream lifecycle, comparison with the older implementation, regression coverage and production verification limits
- [CloudBeaver review](cloudbeaver-review.md): strict findings, real Kubernetes verification, production evidence gaps and rollout decision
- [CloudBeaver security and peer review](cloudbeaver-security-review.md): manual review findings, MD5 protocol/storage assessment and recovery safety boundaries
- [Local setup security review](local-setup-security-review.md): Sonar source-to-sink dispositions, private-state integrity fixes and security-owner gates
- [Cypress Tap and AI Skills](cypress-tap.md): verified capabilities, source pin, installation and validation requirements for local Cypress agent workflows
- [WF-03 test plan](wf-03-test-plan.md): testing assignment and scheduling: business rules, the scenario matrix and its coverage, concurrency design, confirmed defects and open decisions

## Related documents

- [Documentation index](../readme.md)
