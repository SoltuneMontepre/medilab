# WF-03 decisions

| # | Difference | Decision | Step |
| --- | --- | --- | --- |
| 0 | Notation | Initial node, activity final, legend, flow titles | step-01 |
| 1 | Start text | A: "Testing task in the department queue (WF-02 Sample reception and handover)" | step-02 |
| 2 | Hand-over from the queue to SF-10 Scheduling plan and revisions (owner's only) | B: not added | none |
| 3 | "✉ Notify tester" after "Assign tester" (Tuyen's only) | A: kept; noted in wf-03-doc-changes.md | none |
| 4 | "Open recommendation" and "Rank fit machines" ↔ "View the proposed booking for the agreed way" | C: system "Propose a booking of the agreed way in priority order (SF-10 Scheduling plan and revisions)" before tester "View the proposed booking for the agreed way" | step-03 |
| 5 | Decision "Slot before due date?" (System) ↔ "Feasible booking within capacity?" (Tester) | C: System lane, "Feasible booking before the due date?"; noted in wf-03-doc-changes.md | step-04 |
| 6 | "Book slot" ↔ "Accept the proposed booking" | B: "Accept the proposed booking" | step-05 |
| 7 | Head accepts the proposed booking (owner's only) | B: added "Accept the proposed booking for the tester" in the Head lane; Head lane widened to two columns | step-06 |
| 8 | "Reserve machine" ↔ "Reserve tester, required locations and machine if needed together" | B: "Reserve the tester, required locations and machine if needed together" | step-07 |
| 9 | "✉ Remind tester" (System) ↔ "Receive reminder and measure" (Tester) | C: "✉ Remind tester before the booking starts"; measuring left to WF-04; noted in wf-03-doc-changes.md | step-08 |
| 10 | "Review outsourcing" ↔ "Review risk and feasible alternatives", with the hand-over to SF-07 Result dates and priority orders | B: renamed; added flow final "→ SF-07 Result dates and priority orders" and its legend row; WF-05 end kept | step-09 |
| 11 | Planned OverTime (owner's only) | B: added "Record planned OverTime with a reason" above the review; it loops back to the proposal step | step-10 |
| 12 | "Claim task", "Assign tester" ↔ "Claim an authorized department task", "Assign an authorized person" | A: Tuyen's labels kept | none |
| 13 | Demo scenarios | Aligned with the decided Workflow without a separate review, at the owner's request: band titles name their path; DS-03a proposes, views, accepts, reserves; DS-03b accepts and reserves; DS-03c drops "Request slot" and ends at WF-05 Outsourced testing | step-11 |
