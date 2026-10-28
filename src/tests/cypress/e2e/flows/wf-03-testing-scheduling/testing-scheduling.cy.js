import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { pick, search } from "../../../support/form";
import { eventsGone, scheduleState } from "./state";
import {
  ADMINISTRATOR,
  HEAD,
  PARAMETERS,
  PEOPLE,
  TESTER,
  URGENCY,
  assign,
  assignedChromium,
  assignedLead,
  awayFromQuarterHour,
  book,
  bookedLead,
  bookedOnOneMachine,
  checkpointSettings,
  forgetSetting,
  enableReminders,
  openBooking,
  plannedTask,
  receivedSample,
  recommendation,
  queueChromium,
  restoreSettings,
  releaseFixtures,
  resetFixtures,
  runReminders,
  saveSettings,
  scheduleThroughScreen,
  settings,
  storedSettings,
  testOf,
  testingTasks,
} from "./setup";

const REASON = "Ly Van Hung is available for this analysis.";
const ROOM = "Colorimetry room";
const TASK_FIELDS = ["status", "assignee_id", "assigned_by_id", "department_id", "reassign_reason", "planned_start", "planned_end", "write_date"];

const readTask = (task) => () => callAs(ADMINISTRATOR, "medilab.task", "read", [[task.id], TASK_FIELDS]).then(([read]) => read);

const time = (value) => new Date(`${value}Z`).getTime();

beforeEach(() => {
  resetFixtures();
  cy.viewport(1440, 900);
});
afterEach(releaseFixtures);

// Shows the sample's tasks in the department queue.
function findInQueue(sample) {
  cy.visit("/odoo/department-queue");
  search(sample.code, { grouped: true });
  cy.contains(".o_group_header", "Chemistry").click();
}

// Opens a task as its document opens from the to-do list.
function openFromMyTasks(task) {
  cy.visit("/odoo/my-tasks");
  search(task.name);
  cy.contains(".o_data_row", task.name).click();
  cy.get(".o_form_view").should("be.visible");
}

function openTask(task) {
  cy.openRecord({ model: "medilab.task", id: task.id });
}

// Opens the assign dialog from a task's form.
function openAssign() {
  cy.contains(".o_statusbar_buttons button", /^Assign$/).click();
  cy.get(".modal .o_field_widget[name=assignee_id]").should("be.visible");
}

describe("WF-03 baseline assignment and scheduling", () => {
  it("TC-WF03-M lets the head of department assign a sample and the tester book the recommended machine and slot", () => {
    receivedSample([PARAMETERS.chromium, PARAMETERS.ph]).then((sample) => {
      const [chromium] = sample.tests;
      cy.signInAs("head_of_department");
      findInQueue(sample);
      cy.contains(".o_data_row", chromium.task.name).find("button[name=action_assign_sample]").click();
      cy.get(".modal .o_field_widget[name=task_ids] .o_tag").should("have.length", 2);
      pick("assignee_id", "Dang Thi Lan");
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      cy.contains(".o_data_row", chromium.task.name).should("not.exist");
      testingTasks(sample).should((tasks) => {
        expect(tasks).to.have.length(2);
        tasks.forEach((task) => {
          expect(task.status).to.equal("assigned");
          expect(task.assignee_id[1]).to.equal("Dang Thi Lan");
        });
      });

      cy.signInAs("tester");
      awayFromQuarterHour();
      openFromMyTasks(chromium.task);
      cy.get(".o_field_widget[name=recommended_machine_id]").should("be.visible");
      recommendation(chromium).then((recommended) => {
        cy.get(".o_field_widget[name=recommended_machine_id]").should("contain", recommended.recommended_machine_id[1]);
        scheduleThroughScreen();
        cy.get(".o_statusbar_buttons button[name=action_schedule]").should("not.exist");
        openBooking(chromium).then((booking) => {
          expect(booking.status).to.equal("scheduled");
          expect(booking.machine_id[0]).to.equal(recommended.recommended_machine_id[0]);
          expect(booking.starts_at).to.equal(recommended.recommended_start);
          expect(booking.ends_at).to.equal(recommended.recommended_end);

          cy.visit("/odoo/machine-schedule?view_type=list");
          search(booking.machine_id[1], { field: "Machine" });
          cy.contains(".o_data_row", booking.display_name).should("contain", booking.machine_id[1]).and("be.visible");
          call("calendar.event", "read", [[booking.calendar_event_id[0]], ["start", "stop", "partner_ids", "alarm_ids"]]).then(([event]) => {
            expect(event.start).to.equal(booking.starts_at);
            expect(event.stop).to.equal(booking.ends_at);
            call("res.users", "search_read", [[["login", "=", TESTER]]], { fields: ["partner_id"] }).then(([user]) => {
              expect(event.partner_ids).to.include(user.partner_id[0]);
            });
            // The reminder job reminds of the booking; Odoo's own alarm would remind twice.
            expect(event.alarm_ids).to.be.empty;
          });
          cy.readRecord(chromium.task, ["planned_start", "planned_end"]).should((task) => {
            expect(task.planned_start).to.equal(booking.starts_at);
            expect(task.planned_end).to.equal(booking.ends_at);
          });
          cy.visit("/odoo/calendar?view_type=list");
          search(sample.code);
          cy.contains(".o_data_row", `${booking.machine_id[1]}: ${booking.display_name}`).should("be.visible");
        });
      });
    });
  });

  it("TC-WF03-A1 lets a tester claim an unassigned task of their department", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).find("button[name=action_claim]").click();
      cy.contains(".o_data_row", lead.task.name).should("not.exist");
      cy.visit("/odoo/my-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).should("be.visible");
      readTask(lead.task)().should((task) => {
        expect(task.status).to.equal("assigned");
        expect(task.assignee_id[1]).to.equal("Dang Thi Lan");
      });
      cy.readRecord(lead.task, ["assigned_by_id"]).its("assigned_by_id.1").should("eq", "Dang Thi Lan");
    });
  });

  it("TC-WF03-A2 lets the head of department move a task to another person, then to another department, with a reason", () => {
    bookedLead().then(({ sample, test, booking }) => {
      const task = { model: "medilab.task", id: booking.task_id[0] };
      cy.signInAs("head_of_department");
      openTask(task);
      openAssign();
      pick("assignee_id", "Ly Van Hung");
      cy.get(".modal .o_field_widget[name=reason] textarea").type(REASON);
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      readTask(task)().should((read) => {
        expect(read.assignee_id[1]).to.equal("Ly Van Hung");
        expect(read.reassign_reason).to.equal(REASON);
      });
      // The booking goes to the new assignee, planned again in their working time.
      openBooking(test, HEAD).should((moved) => {
        expect(moved.person_id[1]).to.equal("Ly Van Hung");
        expect(moved.status).to.equal("scheduled");
      });
      scheduleState(test).then((state) => {
        const moved = state.bookings.find(({ id }) => id === booking.id);
        expect(state.tasks[0].planned_start).to.equal(moved.starts_at);
        expect(state.tasks[0].planned_end).to.equal(moved.ends_at);
        const event = state.events.find(({ id }) => id === moved.calendar_event_id[0]);
        callAs(ADMINISTRATOR, "res.users", "search_read", [[["login", "=", "demo.chemistry_tester"]]], { fields: ["partner_id"] }).then(([user]) =>
          expect(event.partner_ids).to.deep.equal([user.partner_id[0]]),
        );
        expect(event.start).to.equal(moved.starts_at);
        expect(event.stop).to.equal(moved.ends_at);
      });

      // The task leaves the department, so it is moved from the list, which the head still sees afterwards.
      cy.visit("/odoo/all-tasks");
      search(sample.code);
      cy.contains(".o_data_row", "Lead (Pb)").find("button[name=action_assign_sample]").click();
      pick("department_id", "Microbiology");
      cy.get(".modal .o_field_widget[name=assignee_id] input").should("have.value", "");
      cy.get(".modal .o_field_widget[name=reason] textarea").clear().type("Only Microbiology can test this sample now.");
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      cy.contains(".o_data_row", "Lead (Pb)").should("not.exist");
      readTask(task)().should((read) => {
        expect(read.department_id[1]).to.equal("Microbiology");
        expect(read.status).to.equal("open");
        expect(read.assignee_id).to.equal(false);
      });
      openBooking(test, ADMINISTRATOR).should("eq", null);
      eventsGone([booking.calendar_event_id[0], ...booking.room_event_ids]);
      readTask(task)().should((read) => {
        expect(read.planned_start).to.equal(false);
        expect(read.planned_end).to.equal(false);
      });
    });
  });

  it("TC-WF03-A3 lets the tester cancel a booking, and its slot goes back to the queue", () => {
    assignedChromium().then(({ test }) => {
      // The freed slot must still lie ahead when the test is recommended again.
      awayFromQuarterHour();
      book(test).then((booking) => {
        const eventIds = [booking.calendar_event_id[0], ...booking.room_event_ids];
        cy.signInAs("tester");
        cy.visit(`/odoo/machine-schedule/${booking.id}`);
        cy.intercept("POST", "**/medilab.machine.booking/action_cancel").as("cancelledThroughScreen");
        cy.get(".o_statusbar_buttons button[name=action_cancel]").click();
        cy.wait("@cancelledThroughScreen").its("response.body.error").should("not.exist");
        cy.get(".o_statusbar_buttons button[name=action_cancel]").should("not.exist");
        cy.readRecord(booking, ["status", "calendar_event_id"]).should((read) => {
          expect(read.status).to.equal("cancelled");
          expect(read.calendar_event_id).to.equal(false);
        });
        cy.readRecord({ model: "medilab.task", id: booking.task_id[0] }, ["planned_start", "planned_end"]).should((task) => {
          expect(task.planned_start).to.equal(false);
          expect(task.planned_end).to.equal(false);
        });
        eventsGone(eventIds);
        cy.readRecord(test, ["status"]).its("status").should("eq", "assigned");
        scheduleState(test).then((before) => {
          callRefused("medilab.machine.booking", "action_cancel", [[booking.id]]).should(
            "eq",
            "Only a queued or scheduled booking can be cancelled.",
          );
          scheduleState(test).should("deep.equal", before);
        });
        // The freed slot is offered again, so the test is recommended a slot that ends no later.
        cy.openRecord(test);
        cy.get(".o_statusbar_buttons button[name=action_schedule]").should("be.visible");
        recommendation(test).its("recommended_end").should("be.a", "string").then(time).should("be.at.most", time(booking.ends_at));
        scheduleThroughScreen();
        openBooking(test).should((replacement) => {
          expect(replacement.id).not.to.equal(booking.id);
          expect(replacement.status).to.equal("scheduled");
          expect(replacement.room_event_ids).to.have.length(1);
        });
      });
    });
  });

  it("TC-WF03-A5 creates a machine and step-room booking through Schedule and keeps them together", () => {
    assignedChromium().then(({ sample, test }) => {
      cy.signInAs("tester");
      cy.openRecord(test);
      scheduleThroughScreen();
      openBooking(test).then((booking) => {
        cy.visit(`/odoo/machine-schedule/${booking.id}`);
        cy.get("button.nav-link[name=room_bookings]").click();
        cy.contains(".o_field_widget[name=room_event_ids] .o_data_row", ROOM).should("be.visible");
        cy.readRecord(booking, ["starts_at", "room_event_ids"]).then((read) => {
          call(
            "calendar.event",
            "search_read",
            [
              [
                ["id", "in", read.room_event_ids],
                ["partner_ids.user_ids.login", "=", TESTER],
              ],
            ],
            {
              fields: ["start", "stop", "location_id"],
            },
          ).should((events) => {
            expect(events).to.have.length(1);
            expect(events[0].location_id[1]).to.contain(ROOM);
            // Colour development follows 15 minutes of preparation and lasts 30 minutes.
            expect(time(events[0].start) - time(read.starts_at)).to.equal(15 * 60000);
            expect(time(events[0].stop) - time(read.starts_at)).to.equal(45 * 60000);
          });
          scheduleState(test).then((before) => {
            callRefused("calendar.event", "unlink", [read.room_event_ids]).should("contain", "Move or cancel the machine booking");
            scheduleState(test).should("deep.equal", before);
            callRefused("calendar.event", "write", [read.room_event_ids, { active: false }]).should("contain", "Move or cancel the machine booking");
            scheduleState(test).should("deep.equal", before);
          });
        });
        cy.visit("/odoo/location-bookings?view_type=list");
        search(sample.code);
        cy.contains(".o_data_row", sample.code).should("contain", ROOM).and("be.visible");
        cy.visit("/odoo/calendar?view_type=list");
        search(sample.code);
        cy.contains(".o_data_row", ROOM).should("be.visible");
      });
    });
  });

  it("TC-WF03-E1 baseline / TC-F23-03 rejects a claim from a stale list without changing the winner", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("chemistry_tester");
      cy.visit("/odoo/awaiting-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).should("be.visible");
      callAs(TESTER, "medilab.task", "action_claim", [[lead.task.id]]);
      cy.expectRefusal({
        read: () => scheduleState(lead),
        action: () => cy.contains(".o_data_row", lead.task.name).find("button[name=action_claim]").click(),
        message: `${lead.task.name} is already claimed.`,
      });
      cy.visit("/odoo/awaiting-tasks");
      search(lead.task.name);
      cy.get(".o_list_renderer").should("not.contain", lead.task.name);
      readTask(lead.task)().its("assignee_id.1").should("eq", "Dang Thi Lan");
      cy.visit("/odoo/my-tasks");
      search(lead.task.name);
      cy.get(".o_list_renderer").should("not.contain", lead.task.name);
      cy.signInAs("tester");
      cy.visit("/odoo/my-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).should("be.visible");
    });
  });

  it("TC-WF03-E2 baseline / TC-F23-03 hides another department's task and refuses its claim over RPC", () => {
    receivedSample([PARAMETERS.coliforms]).then(({ tests: [coliforms] }) => {
      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      search(coliforms.task.name);
      cy.get(".o_list_renderer").should("not.contain", coliforms.task.name);
      scheduleState(coliforms).then((before) => {
        callRefused("medilab.task", "action_claim", [[coliforms.task.id]]).should(
          "eq",
          `${coliforms.task.name} waits in a queue you do not belong to.`,
        );
        scheduleState(coliforms).should("deep.equal", before);
      });
      callAs(ADMINISTRATOR, "medilab.task", "read", [[coliforms.task.id], ["status", "assignee_id"]]).should(([task]) => {
        expect(task.status).to.equal("open");
        expect(task.assignee_id).to.equal(false);
      });
    });
  });

  it("TC-WF03-E3 baseline / TC-F23-03 preserves reservations after a missing reason and lets the head retry", () => {
    assignedChromium().then(({ test: lead }) => {
      book(lead);
      cy.signInAs("head_of_department");
      openTask(lead.task);
      openAssign();
      pick("assignee_id", "Ly Van Hung");
      // The screen marks the empty reason as a required field and keeps the dialog open.
      scheduleState(lead).then((before) => {
        cy.get(".modal .o_field_widget[name=reason]").should("not.have.class", "o_field_invalid");
        cy.get(".modal button[name=action_confirm]").click();
        cy.get(".modal .o_field_widget[name=reason]").should("have.class", "o_field_invalid");
        scheduleState(lead).should("deep.equal", before);
      });
      scheduleState(lead).then((before) =>
        refAs(HEAD, PEOPLE.chemistryTester).then((person) => {
          callRefused("medilab.task", "write", [[lead.task.id], { assignee_id: person.id }]).should(
            "eq",
            `Give a reason for moving ${lead.task.name} to another person or department.`,
          );
          scheduleState(lead).should("deep.equal", before);
        }),
      );
      cy.get(".modal .o_field_widget[name=reason] textarea").type(REASON);
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      scheduleState(lead).should((after) => {
        expect(after.tasks[0].assignee_id[1]).to.equal("Ly Van Hung");
        expect(after.tasks[0].reassign_reason).to.equal(REASON);
        expect(after.bookings[0].person_id[1]).to.equal("Ly Van Hung");
        expect(after.events).to.have.length(2);
      });
    });
  });
});

describe("WF-03 feature acceptance criteria", () => {
  let stored;
  beforeEach(() => {
    stored = undefined;
    return checkpointSettings().then((snapshot) => {
      stored = snapshot;
      return enableReminders();
    });
  });
  afterEach(() => restoreSettings(stored));

  it("TC-F22-01 rejects malformed urgency on screen, then saves a valid value through Save", () => {
    settings().then(({ urgency_hours: initial }) => {
      cy.signInAs("administrator");
      cy.visit("/odoo/lab-settings");
      const input = ".o_field_widget[name=urgency_hours] input";
      cy.get(input).should("have.value", String(initial)).clear().type("invalid").blur();
      cy.get(".o_control_panel .o_form_button_save").should("be.visible").click();
      cy.get(".o_field_widget[name=urgency_hours]").should("have.class", "o_field_invalid");
      settings().its("urgency_hours").should("eq", initial);
      cy.get(input)
        .clear()
        .type(String(initial + 1))
        .blur();
      cy.intercept("POST", "**/res.config.settings/execute").as("savedSettings");
      cy.intercept("POST", "**/res.config.settings/onchange").as("reloadedSettings");
      cy.get(".o_control_panel .o_form_button_save").click();
      cy.wait("@savedSettings").its("response.body.error").should("not.exist");
      cy.wait("@reloadedSettings")
        .its("response.body.result.value.urgency_hours")
        .should("eq", initial + 1);
      cy.get(input).should("have.value", String(initial + 1));
      settings()
        .its("urgency_hours")
        .should("eq", initial + 1);
    });
  });

  it("TC-F22-01 RPC refuses settings changes by a tester without changing the stored values", () => {
    storedSettings().then((before) => {
      cy.signInAs("tester");
      callRefused("res.config.settings", "create", [{ urgency_hours: 999 }]).should("match", /not allowed|access/i);
      storedSettings().should("deep.equal", before);
    });
  });

  it("TC-F22-02 keeps the due dates already worked out when the safety margin changes", () => {
    receivedSample().then((before) => {
      testOf(before, PARAMETERS.lead).then((test) => callAs(ADMINISTRATOR, "medilab.sample.test", "read", [[test.id], ["due_date"]]).as("due"));
      settings().then(({ safety_margin_days: margin }) => saveSettings({ safety_margin_days: margin + 1 }));
      receivedSample().then((after) => {
        cy.signInAs("head_of_department");
        cy.get("@due").then(([{ due_date: due }]) => {
          testOf(before, PARAMETERS.lead).then((test) => cy.readRecord(test, ["due_date"]).its("due_date").should("eq", due));
          testOf(after, PARAMETERS.lead).then((test) =>
            cy
              .readRecord(test, ["due_date"])
              .its("due_date")
              .should((later) => expect(time(due) - time(later)).to.equal(86400000)),
          );
        });
      });
    });
  });

  it("TC-F22-03 falls back to the default urgency while none is stored, and audits each change", () => {
    forgetSetting(URGENCY);
    cy.signInAs("administrator");
    cy.visit("/odoo/lab-settings");
    cy.get(".o_field_widget[name=urgency_hours] input").should("have.value", "24");
    saveSettings({ urgency_hours: 48 });
    saveSettings({ urgency_hours: 36 });
    settings().its("urgency_hours").should("eq", 36);
    call(
      "medilab.audit.entry",
      "search_read",
      [
        [
          ["document_model", "=", "ir.config_parameter"],
          ["note", "=", URGENCY],
        ],
      ],
      {
        fields: ["action", "user_id"],
        order: "id desc",
        limit: 2,
      },
    ).should((entries) => {
      expect(entries.map((entry) => entry.action)).to.deep.equal(["edit", "create"]);
      entries.forEach((entry) => expect(entry.user_id[1]).to.equal("Phan Minh Quan"));
    });
  });

  it("TC-F24-02 RPC queue orders urgent work before earlier arrivals and other work by queue time", () => {
    saveSettings({ urgency_hours: 12 * 24 });
    const now = Date.now();
    assignedChromium({ days: 60 }).then(({ test: ordinary }) =>
      assignedChromium({ days: 12 }).then(({ test: urgent }) => {
        queueChromium(ordinary, now - 60000);
        queueChromium(urgent, now);
        assignedChromium({ days: 60 }).then(({ test: trigger }) => book(trigger));
        openBooking(urgent).then((first) =>
          openBooking(ordinary).then((second) => {
            expect(first.machine_id).to.deep.equal(second.machine_id);
            expect(time(first.ends_at)).to.be.at.most(time(second.starts_at));
            expect(time(first.ends_at) - time(first.starts_at)).to.equal(60 * 60000);
          }),
        );
      }),
    );
    assignedChromium({ days: 60 }).then(({ test: older }) =>
      assignedChromium({ days: 60 }).then(({ test: newer }) => {
        queueChromium(newer, now - 120000);
        queueChromium(older, now - 180000);
        assignedChromium({ days: 60 }).then(({ test: trigger }) => book(trigger));
        openBooking(older).then((first) =>
          openBooking(newer).then((second) => {
            expect(first.machine_id).to.deep.equal(second.machine_id);
            expect(time(first.ends_at)).to.be.at.most(time(second.starts_at));
            expect(time(second.ends_at) - time(second.starts_at)).to.equal(60 * 60000);
          }),
        );
      }),
    );
    bookedLead().then(({ booking }) =>
      callAs(ADMINISTRATOR, "medilab.parameter.method.machine", "search_read", [[["machine_id", "=", booking.machine_id[0]]]], {
        fields: ["run_minutes"],
      }).then(([link]) => {
        expect((time(booking.ends_at) - time(booking.starts_at)) / 60000).to.equal(Math.ceil(link.run_minutes / 15) * 15);
      }),
    );
  });

  it("TC-F24-03 refuses moving a booking onto another booking of the same machine", () => {
    bookedOnOneMachine().then(([taken, booking]) => {
      cy.signInAs("tester");
      const test = { id: booking.sample_test_id[0] };
      scheduleState(test).then((before) => {
        callRefused("medilab.machine.booking", "write", [[booking.id], { starts_at: taken.starts_at }]).should(
          "eq",
          `${booking.machine_id[1]} is not free for ${booking.display_name} at that time.`,
        );
        scheduleState(test).should("deep.equal", before);
      });
      cy.readRecord(booking, ["starts_at", "ends_at", "status"]).should("deep.include", {
        starts_at: booking.starts_at,
        ends_at: booking.ends_at,
        status: "scheduled",
      });
    });
  });

  it("TC-F25-02 reminds the person of a planned task once, 15 minutes before it starts", () => {
    plannedTask().then((task) => {
      runReminders();
      runReminders();
      cy.signInAs("tester");
      call(
        "mail.message",
        "search_read",
        [
          [
            ["model", "=", "medilab.task"],
            ["res_id", "=", task.id],
            ["needaction", "=", true],
          ],
        ],
        {
          fields: ["subject", "notification_ids"],
        },
      ).should((messages) => {
        expect(messages).to.have.length(1);
        expect(messages[0].subject).to.equal(task.name);
      });
      callAs(ADMINISTRATOR, "mail.notification", "search_count", [
        [
          ["mail_message_id.model", "=", "medilab.task"],
          ["mail_message_id.res_id", "=", task.id],
          ["res_partner_id.user_ids.login", "=", TESTER],
        ],
      ]).should("eq", 1);
    });
  });

  it("TC-F25-03 notifies nobody of an event the administrator turned off, and keeps a mandatory event on", () => {
    cy.signInAs("administrator");
    cy.visit("/odoo/notification-events");
    cy.contains(".o_data_row", "task.reminder").click();
    cy.get(".o_field_widget[name=enabled] input").uncheck();
    cy.get(".o_form_button_save").click();
    cy.get(".o_form_button_save").should("not.be.visible");
    plannedTask().then((task) => {
      runReminders();
      callAs(ADMINISTRATOR, "mail.message", "search_count", [
        [
          ["model", "=", "medilab.task"],
          ["res_id", "=", task.id],
        ],
      ]).should("eq", 0);
    });
    cy.visit("/odoo/notification-events");
    cy.contains(".o_data_row", "test_result.rejected").click();
    cy.get(".o_field_widget[name=enabled] input").should("be.disabled");
    refAs(ADMINISTRATOR, "sol_laboratory.event_test_result_rejected").then((event) =>
      cy.readRecord(event, ["enabled", "mandatory", "write_date"]).then((before) => {
        callRefused("mail.message.subtype", "write", [[event.id], { enabled: false }]).should("eq", "A mandatory event cannot be turned off.");
        cy.readRecord(event, ["enabled", "mandatory", "write_date"]).should("deep.equal", before);
      }),
    );
  });
});
