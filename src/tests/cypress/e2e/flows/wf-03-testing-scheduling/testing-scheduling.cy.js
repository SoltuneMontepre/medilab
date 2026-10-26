import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import {
  ADMINISTRATOR,
  HEAD,
  PARAMETERS,
  PEOPLE,
  TESTER,
  URGENCY,
  assign,
  awayFromQuarterHour,
  bookedLead,
  bookedOnOneMachine,
  forgetSetting,
  openBooking,
  plannedTask,
  receivedSample,
  recommendation,
  restoreSettings,
  runReminders,
  saveSettings,
  settings,
  storedSettings,
  testOf,
  testingTasks,
} from "./setup";

const REASON = "Ly Van Hung runs the ICP-MS this week.";
const ROOM = "Sample preparation room";
const TASK_FIELDS = ["status", "assignee_id", "department_id", "reassign_reason", "write_date"];

const readTask = (task) => () => callAs(ADMINISTRATOR, "medilab.task", "read", [[task.id], TASK_FIELDS]).then(([read]) => read);

const time = (value) => new Date(`${value}Z`).getTime();

// Picks a many2one value in the open dialog.
function pick(field, text) {
  cy.get(`.modal .o_field_widget[name=${field}] input`).clear().type(text);
  cy.contains(".o-autocomplete--dropdown-item a", text).click();
}

// Filters a list to the records whose name contains the text, so a long list does not page them out.
function search(text) {
  cy.get(".o_searchview_input").type(text);
  cy.get(".o_searchview_autocomplete .o-dropdown-item").first().click();
  cy.contains(".o_searchview_facet", text).should("be.visible");
}

// Shows the sample's tasks in the department queue.
function findInQueue(sample) {
  cy.visit("/odoo/department-queue");
  search(sample.code);
  cy.contains(".o_group_header", "Chemistry").click();
}

// Opens a task as its document opens from the to-do list.
function openFromMyTasks(task) {
  cy.visit("/odoo/my-tasks");
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

describe("WF-03 Testing assignment and scheduling", () => {
  it("TC-WF03-M lets the head of department assign a sample and the tester book the recommended machine and slot", () => {
    receivedSample([PARAMETERS.lead, PARAMETERS.ph]).then((sample) => {
      const [lead] = sample.tests;
      cy.signInAs("head_of_department");
      findInQueue(sample);
      cy.contains(".o_data_row", lead.task.name).find("button[name=action_assign_sample]").click();
      cy.get(".modal .o_field_widget[name=task_ids] .o_tag").should("have.length", 2);
      pick("assignee_id", "Dang Thi Lan");
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      cy.contains(".o_data_row", lead.task.name).should("not.exist");
      testingTasks(sample).should((tasks) => {
        expect(tasks).to.have.length(2);
        tasks.forEach((task) => {
          expect(task.status).to.equal("assigned");
          expect(task.assignee_id[1]).to.equal("Dang Thi Lan");
        });
      });

      cy.signInAs("tester");
      openFromMyTasks(lead.task);
      cy.get(".o_field_widget[name=recommended_machine_id]").should("be.visible");
      awayFromQuarterHour();
      recommendation(lead).then((recommended) => {
        cy.get(".o_field_widget[name=recommended_machine_id]").should("contain", recommended.recommended_machine_id[1]);
        cy.get(".o_statusbar_buttons button[name=action_schedule]").click();
        cy.get(".o_statusbar_buttons button[name=action_schedule]").should("not.exist");
        openBooking(lead).then((booking) => {
          expect(booking.status).to.equal("scheduled");
          expect(booking.machine_id[0]).to.equal(recommended.recommended_machine_id[0]);
          expect(booking.starts_at).to.equal(recommended.recommended_start);
          expect(booking.ends_at).to.equal(recommended.recommended_end);

          cy.visit("/odoo/machine-schedule?view_type=list");
          cy.contains(".o_data_row", `${sample.code}: Lead (Pb)`).should("contain", booking.machine_id[1]);
          call("calendar.event", "read", [[booking.calendar_event_id[0]], ["start", "stop", "partner_ids", "alarm_ids"]]).then(([event]) => {
            expect(event.start).to.equal(booking.starts_at);
            expect(event.stop).to.equal(booking.ends_at);
            // The reminder job reminds of the booking; Odoo's own alarm would remind twice.
            expect(event.alarm_ids).to.be.empty;
          });
          cy.readRecord(lead.task, ["planned_start", "planned_end"]).should((task) => {
            expect(task.planned_start).to.equal(booking.starts_at);
            expect(task.planned_end).to.equal(booking.ends_at);
          });
        });
      });
    });
  });

  it("TC-WF03-A1 lets a tester claim an unassigned task of their department", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      cy.contains(".o_data_row", lead.task.name).find("button[name=action_claim]").click();
      cy.contains(".o_data_row", lead.task.name).should("not.exist");
      cy.visit("/odoo/my-tasks");
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
    });
  });

  it("TC-WF03-A3 lets the tester cancel a booking, and its slot goes back to the queue", () => {
    awayFromQuarterHour();
    bookedLead().then(({ test, booking }) => {
      cy.signInAs("tester");
      cy.visit(`/odoo/machine-schedule/${booking.id}`);
      cy.get(".o_statusbar_buttons button[name=action_cancel]").click();
      cy.get(".o_statusbar_buttons button[name=action_cancel]").should("not.exist");
      cy.readRecord(booking, ["status", "calendar_event_id"]).should((read) => {
        expect(read.status).to.equal("cancelled");
        expect(read.calendar_event_id).to.equal(false);
      });
      cy.readRecord({ model: "medilab.task", id: booking.task_id[0] }, ["planned_start"]).its("planned_start").should("eq", false);
      // The freed slot is offered again, so the test is recommended a slot that ends no later.
      cy.openRecord(test);
      cy.get(".o_statusbar_buttons button[name=action_schedule]").should("be.visible");
      recommendation(test).its("recommended_end").should("be.a", "string").then(time).should("be.at.most", time(booking.ends_at));
    });
  });

  // While the preparation room is busy the scheduler prefers the AAS machines, so the test reads a seeded ICP-MS booking.
  it("TC-WF03-A5 books the room of a step with its machine, on the tester's calendar, and keeps them together", () => {
    cy.signInAs("tester");
    refAs(TESTER, "sol_demo.demo_machine_booking_lead_room_booked").then((booking) => {
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
          // Filtering takes the first 15 minutes; digesting in the room takes an hour.
          expect(time(events[0].start) - time(read.starts_at)).to.equal(15 * 60000);
          expect(time(events[0].stop) - time(read.starts_at)).to.equal(75 * 60000);
        });
        callRefused("calendar.event", "unlink", [read.room_event_ids]).should("contain", "Move or cancel the machine booking");
        cy.readRecord(booking, ["room_event_ids"]).its("room_event_ids").should("deep.equal", read.room_event_ids);
      });
    });
  });

  it("TC-WF03-E1 tells a second tester claiming the same task that it is already claimed", () => {
    receivedSample().then(({ tests: [lead] }) => {
      cy.signInAs("chemistry_tester");
      cy.visit("/odoo/awaiting-tasks");
      cy.contains(".o_data_row", lead.task.name).should("be.visible");
      callAs(TESTER, "medilab.task", "action_claim", [[lead.task.id]]);
      cy.expectRefusal({
        read: readTask(lead.task),
        action: () => cy.contains(".o_data_row", lead.task.name).find("button[name=action_claim]").click(),
        message: `${lead.task.name} is already claimed.`,
      });
      cy.visit("/odoo/awaiting-tasks");
      cy.get(".o_list_renderer").should("not.contain", lead.task.name);
    });
  });

  it("TC-WF03-E2 refuses claiming a task of another department", () => {
    receivedSample([PARAMETERS.coliforms]).then(({ tests: [coliforms] }) => {
      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      cy.get(".o_list_renderer").should("not.contain", coliforms.task.name);
      callRefused("medilab.task", "action_claim", [[coliforms.task.id]]).should(
        "eq",
        `${coliforms.task.name} waits in a queue you do not belong to.`,
      );
      callAs(ADMINISTRATOR, "medilab.task", "read", [[coliforms.task.id], ["status", "assignee_id"]]).should(([task]) => {
        expect(task.status).to.equal("open");
        expect(task.assignee_id).to.equal(false);
      });
    });
  });

  it("TC-WF03-E3 refuses moving a task to another person without a reason", () => {
    receivedSample().then((sample) => {
      assign(sample);
      const [lead] = sample.tests;
      cy.signInAs("head_of_department");
      openTask(lead.task);
      openAssign();
      pick("assignee_id", "Ly Van Hung");
      // The screen marks the empty reason as a required field and keeps the dialog open.
      readTask(lead.task)().then((before) => {
        cy.get(".modal .o_field_widget[name=reason]").should("not.have.class", "o_field_invalid");
        cy.get(".modal button[name=action_confirm]").click();
        cy.get(".modal .o_field_widget[name=reason]").should("have.class", "o_field_invalid");
        readTask(lead.task)().should("deep.equal", before);
      });
      refAs(HEAD, PEOPLE.chemistryTester).then((person) =>
        callRefused("medilab.task", "write", [[lead.task.id], { assignee_id: person.id }]).should(
          "eq",
          `Give a reason for moving ${lead.task.name} to another person or department.`,
        ),
      );
    });
  });
});

describe("WF-03 feature acceptance criteria", () => {
  let stored;
  beforeEach(() => storedSettings().then((parameters) => (stored = parameters)));
  afterEach(() => restoreSettings(stored));

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

  it("TC-F24-02 books the run time in whole 15-minute slots, urgent tests first, then first in first out", () => {
    // A test due within the urgency hours is urgent: twelve days makes the nearer test urgent and leaves the other.
    saveSettings({ urgency_hours: 12 * 24 });
    receivedSample([PARAMETERS.lead], { days: 60 }).then((later) =>
      receivedSample([PARAMETERS.lead], { days: 12 }).then((urgent) => {
        assign(later);
        assign(urgent);
        callAs(TESTER, "medilab.sample.test", "action_schedule", [[later.tests[0].id, urgent.tests[0].id]]);
        openBooking(later.tests[0]).then((notUrgent) =>
          openBooking(urgent.tests[0]).its("ends_at").then(time).should("be.at.most", time(notUrgent.ends_at)),
        );
      }),
    );
    receivedSample().then((older) =>
      receivedSample().then((newer) => {
        assign(older);
        assign(newer);
        callAs(TESTER, "medilab.sample.test", "action_schedule", [[older.tests[0].id, newer.tests[0].id]]);
        openBooking(older.tests[0]).then((first) =>
          openBooking(newer.tests[0]).then((second) => {
            expect(time(first.ends_at)).to.be.at.most(time(second.ends_at));
            callAs(
              ADMINISTRATOR,
              "medilab.parameter.method.machine",
              "search_read",
              [[["machine_id", "in", [first.machine_id[0], second.machine_id[0]]]]],
              {
                fields: ["machine_id", "run_minutes"],
              },
            ).then((links) =>
              [first, second].forEach((booking) => {
                const { run_minutes: run } = links.find((link) => link.machine_id[0] === booking.machine_id[0]);
                const minutes = (time(booking.ends_at) - time(booking.starts_at)) / 60000;
                expect(minutes, `${booking.machine_id[1]} slot`).to.equal(Math.ceil(run / 15) * 15);
              }),
            );
          }),
        );
      }),
    );
  });

  it("TC-F24-03 refuses moving a booking onto another booking of the same machine", () => {
    bookedOnOneMachine().then(([taken, booking]) => {
      cy.signInAs("tester");
      callRefused("medilab.machine.booking", "write", [[booking.id], { starts_at: taken.starts_at }]).should(
        "eq",
        `${booking.machine_id[1]} is not free for ${booking.display_name} at that time.`,
      );
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
      callRefused("mail.message.subtype", "write", [[event.id], { enabled: false }]).should("eq", "A mandatory event cannot be turned off."),
    );
  });
});
