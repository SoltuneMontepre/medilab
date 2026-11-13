# Scheduling

Stories: US-T01, US-T02, US-T03, US-T19, US-T20, US-T21, US-HD03, US-HD04, US-HD05, US-HD09, US-HD12, US-HD14, US-LH04

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

A measurement in progress past its end keeps its machine from taking a new booking until its result is entered or it is marked finished. The scheduled job `machine_bookings.overrun` checks every 15 minutes for scheduled and in-progress bookings past their end and sends the mandatory `machine_booking.overrun` notification once for each end: to the testers and heads of the booking and of the next bookings on its machine, the bookings of the earliest later interval, which the notification names as at risk. The booking's form says its end has passed, and the form of each scheduled booking on a held machine says it is at risk.

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
| Override | The head of the department testing a sample test may override its internal due date with a reason, until its result is entered. The override stays until the head clears it; a changed committed date recalculates only automatic dates and reports a conflict for an override later than the automatic date. |
| Working days | The company's working calendar gives the working days: its working hours, minus company-wide time off. The administrator keeps the public holidays as company-wide time off; one counted as working time is a working day. A due date on a non-working day, automatic or overridden, is kept and reported. |
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

The calibration, maintenance and recent-repair warning windows are three independent settings, each 7 days by default. They warn when planning or starting within the window and never allow a blocked booking. A booking warns when it ends within the calibration window before the end of its machine's calibration date or within the maintenance window before the end of its maintenance due date, and when it starts within the recent-repair window after the day of the machine's latest repair; the booking's form shows the warning. A window of 0 days turns its warning off. Returning a machine to in use after a repair requires a calibration or maintenance record dated after the repair.

### Data

The tables are drawn in [laboratory.prisma](../infrastructure/database/laboratory/laboratory.prisma). A department's plan is its proposed bookings and has no table of its own. A sample test's arrival is when its department received the sample, and its planned finish is the end of its booking.

| Table | Holds |
| --- | --- |
| `medilab_machine_method` | A machine linked to a testing method, with the booking duration and the capacity in samples |
| `medilab_parameter_method` | The duration and capacity of a way whose method has no machine |
| `medilab_machine_booking` | A booking: its sample test, method, tester, interval, machine when needed, state and pinned flag |
| `calendar_event` | The tester's event of a scheduled booking, and a reservation of each bookable step location |
| `medilab_plan_revision`, `medilab_plan_revision_move` | A plan revision and each booking it moves, with the new interval, the approving head and the held-back or conflict state |
| `medilab_parameter_authorization` | The parameters the Lab Head authorized each person to test |
| `medilab_overtime` | Planned OverTime of a tester |
| `medilab_location_unavailability` | Intervals a location cannot be used |
| `medilab_machine_service` | Done and planned services, with the downtime a planned maintenance reserves |
| `medilab_test_request`, `medilab_committed_date_change` | The requested and committed return dates, and each change of the committed date with the customer's confirmation |
| `medilab_sample_test` | The internal due date and the head's override with its reason, the urgent mark with its reason, and the at-risk flag |
| `medilab_test_result` | The booking a result was measured in, and the head's assessment of an interrupted result |

The three warning windows, the due-soon threshold and the safety margin are settings.

### Upgrading today's bookings

The upgrade keeps every booking, calendar event and reminder, and creates nothing the laboratory did not record.

| Data | After the upgrade |
| --- | --- |
| Way-and-machine links | One machine-and-method link for each machine and method of the ways linked to it, with capacity 1. Its duration is the run time of those links, or the longest of them when they differ; the upgrade logs each such link. The way-and-machine table is dropped, and the permissions of its links move to the new links, so roles keep them. |
| Ways | Every way of a method linked to a machine can be booked on that machine. An in-house way whose method has no machine keeps capacity 1 and an empty duration, and cannot be booked until it has one; the upgrade logs each. |
| Queued bookings | Proposed, keeping their sample test, task, department and tester. They had no interval, calendar event or location reservation; the first recalculation of the plan places them. |
| Scheduled, in-progress, done and cancelled bookings | Unchanged, with their machine, interval, calendar event, location reservations and reminders; reminders follow their calendar event. None is pinned. Their method is filled from the sample test's way. |
| Queue order | The time a booking joined the queue and its copied due date are dropped: the plan orders by priority class, committed return date and arrival. |
| Results | Linked to the booking of their sample test whose machine and start they match, when exactly one does; otherwise left without a booking. None is interrupted. |
| Test requests | The expected date becomes the committed return date. The requested date stays empty. |
| Machine services | Every existing record is a done service without downtime. |

No authorization, OverTime, location unavailability, plan revision or urgent mark is created. After the upgrade:

- The administrator sets the capacity of each machine-and-method link of a machine that takes several samples in one load, such as an ICP-MS or an incubator, and checks the durations the upgrade logged.
- The administrator enters the duration of each logged in-house way without a machine, and removes a machine-and-method link where a machine must not run every way of that method.
- The Lab Head enters the authorization list. Existing assignments and bookings stay, but nobody is assigned, claims or is booked for a parameter they are not authorized for.

## Related documents

- [Testing schedule](../business/testing-schedule.md)
- [Laboratory overview](../functional/laboratory_module/overview.md#testing-work-and-scheduling)
- [Tester](../functional/laboratory_module/features/tester.md)
- [Head of department](../functional/laboratory_module/features/head-of-department.md)
- [Shared technical features](../functional/shared.md#sh-11-schedules-and-reminders)
- [Specs](readme.md)
