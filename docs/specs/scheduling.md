# Scheduling

Stories: US-T01, US-T02, US-T03, US-T19, US-T20, US-T21, US-HD03, US-HD04, US-HD05, US-HD12, US-HD14

## Goal

Plan every received sample test of a department on the people, machines and rooms it needs, so that it finishes before its internal due date; give urgent work room without silently breaking a date promised to another customer; and keep the plan explainable, so that anyone can see why a booking sits where it does.

## Design

### Bookings

| Rule | Description |
| --- | --- |
| Booking | A booking schedules one sample test, its sample, parameter and agreed way of testing, for one authorized tester and one interval. It uses a machine only when the way needs one, and reserves every bookable location the method's steps name, each for its step interval in step order. |
| Needing a machine | A way needs a machine when its testing method is linked to at least one machine. A way whose method has no machine link needs none. |
| Duration | The machine-and-method link gives the booking duration on that machine. It covers preparation, measurement and the time to repeat a failed measurement, set by the laboratory from experience. A way that needs no machine has its own duration and capacity, capacity 1 by default. Durations round up to 15-minute slots. |
| No attempt counting | The system does not count or limit measurement attempts. A retest is a new result of the same sample test with a new booking. |
| States | A booking is proposed, scheduled, in progress, done or cancelled. A proposed booking is a slot of the plan and reserves nothing; accepting it makes it scheduled, which reserves its tester, machine and locations. |
| Accepting | Accepting a booking reserves its tester, machine and locations together, or nothing when any of them is taken meanwhile. |
| Eligibility | A sample test can be booked only once its sample is received by its department, is not held for the customer's agreement and is not cancelled. The tester must be on the Lab Head's authorization list for its parameter. |
| Machine conditions | A machine booking needs valid calibration and cannot end after the machine's calibration validity. Planned maintenance reserves machine time; overdue maintenance blocks new bookings until completion. A machine under repair or retired gets no booking. |

### Sharing a machine

Bookings may share a machine for exactly the same interval when their ways use the same testing method on that machine. The machine-and-method link gives a capacity in samples, 1 by default. Several parameters of one sample measured together take one place. Nothing joins a machine once its interval has started: a sample test that misses the start waits for a later interval.

A machine that takes several samples in one load, such as an ICP-MS with an autosampler or an incubator, is shared this way. For example, ICP-MS-01 is linked to a metals method by ICP-MS with a duration of 4 hours and a capacity of 20 samples. Pb, Cd and As are three ways of testing that use this method. Measuring Pb, Cd and As on 20 samples in one load gives 60 bookings with the same machine and interval, and they take 20 places. A 21st sample waits for the next interval, and so does a sample test of another method, even if the machine has places left.

### Releasing the machine

A booking holds its machine until the tester enters its result or marks the measurement finished, whichever comes first, which frees the machine early. Bookings sharing the interval free their places one by one. When a booking's end passes without either, the machine stays held, the next bookings on it are flagged at risk, and the tester and the head of department are notified; nothing moves by itself.

### Plan

Each department has a proposed plan: the system places every received, not-started sample test of the department in a proposed booking with its required resources. The plan is recalculated when work arrives, a booking changes, a resource becomes unavailable or a customer date changes. Testers and heads accept proposed bookings to schedule them. Scheduled bookings move only through an approved plan revision.

The plan places sample tests one at a time in priority order, each in the earliest interval where every required resource is free, so the same inputs always give the same plan and each placement can be explained. Pinned bookings are placed first, where the head put them.

### Priority

| Class | Sample tests |
| --- | --- |
| Urgent | An accepted priority order, or a test its tester or head marked urgent with a reason |
| Due soon | A test whose internal due date is within the configured threshold, 24 hours by default |
| Normal | Every other test |

Within a class, the earlier committed return date goes first, then the earlier arrival.

### Dates

| Rule | Description |
| --- | --- |
| Committed return date | The test request carries the committed return date Sales promised the customer. Only Sales changes it, with the customer's agreement, recording the old date, the new date and the confirmation. |
| Internal due date | A sample test's internal due date is its committed return date minus the safety margin, 2 days by default, at the end of the company-local day. A margin change does not rewrite stored dates. |
| Override | The head of department may override an internal due date with a reason. The override stays until the head clears it; a changed committed date recalculates only automatic dates and reports conflicts with overrides. |
| Planned finish | The plan gives each sample test its planned finish: the end of its booking. A sample test meets its internal due date when its result is submitted by then. The safety margin is kept for result approval and report signing. |
| At risk | A sample test is at risk when its planned finish is after its internal due date, when no free slot lets it finish by then, or when its booking overran. Its tester and head are notified when the risk appears, then in a daily consolidated summary until it is resolved. Overdue approvals are reminded through their signing tasks. Only a risk to the committed return date starts the Sales workflow; internal-only changes do not notify the customer. |

### Plan revisions

A recalculation that moves scheduled bookings becomes a plan revision, such as when urgent work needs a slot that other bookings hold. The revision lists every moved booking with its new slot, its internal due date and its committed return date. The head of each affected department approves the moves in their department.

A move whose planned finish passes its internal due date would miss a committed return date. Such a move is held back, and its booking keeps its slot, until Sales records the customer's agreement to a new date. The other moves are recalculated without it and can be applied. When the customer agrees, the held move becomes a new revision; when the customer refuses, the booking stays where it is. The head may instead free capacity, such as with planned OverTime or another machine linked to the same method, and recalculate.

A booking the head places or moves by hand is pinned: plan revisions do not move it and report a conflict instead.

For example, GC-01 has two 4-hour intervals on Wednesday. Z holds the morning and Y the afternoon; both are normal tests with the committed return date Friday, so both have the internal due date Wednesday. On Tuesday at 16:00, urgent sample X arrives with the same dates. The revision proposes X on Wednesday morning, Z on Wednesday afternoon and Y on Thursday morning. Y's move passes its internal due date, so it is held back and Sales asks Y's customer for a new date. Recalculated without moving Y, GC-01 has no Wednesday interval left, so X gets Thursday morning and is flagged at risk. The head of chemistry records OverTime for the tester on Wednesday from 17:00 to 21:00; the recalculated revision puts X in the morning, Z in the afternoon and Y in the evening, all before Wednesday's end, and the head approves it without asking any customer.

### Feasibility check

The feasibility check only reads: it simulates in-house resources and outsourced turnaround, including transport and processing, and moves or reserves nothing. The latest branch finish plus the safety margin gives the return estimate. A missing outsourced turnaround marks the estimate incomplete. The check explains infeasibility and gives the earliest feasible date. A date the head keeps despite infeasibility stays flagged at risk and implies no reserved resources. While Sales waits for the customer's agreement to a changed date or way, the sample test is flagged at risk and keeps its accepted way; nothing is booked on an unapproved way or subcontractor.

### Interruptions

| Rule | Description |
| --- | --- |
| People and rooms | Approved leave or an unavailable required location returns the not-started bookings it overlaps to the plan and notifies the head. The system does not assign another person by itself. |
| Machines | A machine that breaks down or loses calibration during a booking ends that booking. The data recorded so far is kept as an interrupted result, and the head assesses it as usable, needing a retest or needing more sample. A retest is a new result with a new booking, on another machine only when that machine is linked to the same method. |
| Cancelling | Cancelling a sample test ends only its own booking. Bookings sharing its machine interval continue unchanged; a measurement already started keeps its place on the machine until the interval ends, and the cancelled test keeps any recorded data with its cancellation reason. |

### Outside working hours

The head records planned OverTime for a tester, an outside-hours interval and a reason; the tester can then be booked in that interval. The scheduler never creates, moves or recalculates OverTime: moving or cancelling a booking leaves it for the head to change. OverTime extends only the tester's availability; machines and locations keep their own. Only planned OverTime is recorded, not actual hours or payroll.

### Warnings

The calibration, maintenance and recent-repair warning windows are three independent settings, each 7 days by default. They warn when planning or starting within the window and never allow a blocked booking. Returning a machine to in use after a repair requires a calibration or maintenance record dated after the repair.

## Related documents

- [Testing schedule](../business/testing-schedule.md)
- [Laboratory overview](../functional/laboratory_module/overview.md#testing-work-and-scheduling)
- [Tester](../functional/laboratory_module/features/tester.md)
- [Head of department](../functional/laboratory_module/features/head-of-department.md)
- [Shared technical features](../functional/shared.md#sh-11-schedules-and-reminders)
- [Specs](readme.md)
