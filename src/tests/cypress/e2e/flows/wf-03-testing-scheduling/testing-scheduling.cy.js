import { call, callAs, callRefused, refAs } from "../../../support/odoo";
import { openMenu, pick, search } from "../../../support/form";
import { MENU } from "../../../support/menus";
import { step } from "../../../support/steps";
import { eventsGone, scheduleState } from "./state";
import {
  ADMINISTRATOR,
  HEAD,
  OTHER_TESTER,
  PARAMETERS,
  PEOPLE,
  TESTER,
  URGENCY,
  approveThroughScreen,
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
  notices,
  openBooking,
  partnerOf,
  plannedTask,
  receivedSample,
  recommendation,
  restoreSettings,
  releaseFixtures,
  resetFixtures,
  runReminders,
  saveSettings,
  settings,
  storedSettings,
  testOf,
  testingTasks,
} from "./setup";

const ASSIGNED = "sol_laboratory.event_task_assigned";
const APPROVED = "sol_laboratory.event_machine_booking_approved";
const REMINDER = "task.reminder";
const REASON = "Ly Van Hung is available for this analysis.";
const ROOM = "Colorimetry room";
const TASK_FIELDS = ["status", "assignee_id", "assigned_by_id", "department_id", "reassign_reason", "planned_start", "planned_end", "write_date"];

const readTask = (task) => () => callAs(ADMINISTRATOR, "medilab.task", "read", [[task.id], TASK_FIELDS]).then(([read]) => read);

const time = (value) => new Date(`${value}Z`).getTime();

beforeEach(resetFixtures);
afterEach(releaseFixtures);

function openTask(task) {
  cy.openRecord({ model: "medilab.task", id: task.id });
}

// Opens the assign dialog from a task's form.
function openAssign() {
  cy.contains(".o_statusbar_buttons button", /^Assign$/).click();
  cy.get(".modal .o_field_widget[name=assignee_id]").should("be.visible");
}

describe("WF-03 baseline assignment and scheduling", () => {
  it("TC-WF03-M partial lets the head of department assign a sample, then approve the recommended machine and slot the tester sees", () => {
    receivedSample([PARAMETERS.chromium, PARAMETERS.ph]).then((sample) => {
      const [chromium] = sample.tests;
      step("The head of department finds the sample's tasks in the department queue");
      cy.signInAs("head_of_department");
      openMenu(MENU.tasks, MENU.departmentQueue);
      search(sample.code, { grouped: true });
      cy.contains(".o_group_header", "Chemistry").click();
      step("The head assigns the sample to a tester");
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

      // Assigning tells the tester of each task.
      partnerOf(TESTER).then((tester) =>
        sample.tests.forEach((test) =>
          notices(ASSIGNED, test.task).should(({ partners }) => expect(partners).to.deep.equal([tester])),
        ),
      );

      step("The tester opens the task from My Tasks");
      cy.signInAs("tester");
      awayFromQuarterHour();
      openMenu(MENU.tasks, MENU.myTasks);
      search(chromium.task.name);
      cy.contains(".o_data_row", chromium.task.name).click();
      cy.get(".o_form_view").should("be.visible");
      step("The tester sees the recommended slot, which the head of department approves");
      cy.get(".o_field_widget[name=recommended_machine_id]").should("be.visible");
      // The tester reads the proposed slot but cannot reserve it, and it reserves nothing.
      cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("not.exist");
      openBooking(chromium).should((proposed) => {
        expect(proposed.status).to.equal("proposed");
        expect(proposed.calendar_event_id).to.equal(false);
      });
      recommendation(chromium).then((recommended) => {
        cy.get(".o_field_widget[name=recommended_machine_id]").should("contain", recommended.recommended_machine_id[1]);
        cy.signInAs("head_of_department");
        cy.openRecord(chromium);
        approveThroughScreen();
        cy.signInAs("tester");
        openBooking(chromium).then((booking) => {
          expect(booking.status).to.equal("scheduled");
          expect(booking.machine_id[0]).to.equal(recommended.recommended_machine_id[0]);
          expect(booking.starts_at).to.equal(recommended.recommended_start);
          expect(booking.ends_at).to.equal(recommended.recommended_end);
          partnerOf(TESTER).then((tester) =>
            notices(APPROVED, booking).should(({ partners }) => expect(partners).to.deep.equal([tester])),
          );

          step("The booking shows in the machine schedule and in the tester's calendar");
          openMenu(MENU.laboratory, MENU.schedule, MENU.machineSchedule);
          cy.get(".o_switch_view.o_list").click();
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
          openMenu(MENU.calendar);
          cy.get(".o_switch_view.o_list").click();
          search(sample.code);
          cy.contains(".o_data_row", `${booking.machine_id[1]}: ${booking.display_name}`).should("be.visible");
        });
      });
    });
  });

  it("TC-WF03-A1 partial lets a tester claim an unassigned task of their department", () => {
    receivedSample().then(({ tests: [lead] }) => {
      step("The tester claims an unassigned task of their department");
      cy.signInAs("tester");
      cy.visit("/odoo/awaiting-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).find("button[name=action_claim]").click();
      cy.contains(".o_data_row", lead.task.name).should("not.exist");
      step("The task shows in the tester's My Tasks, assigned to them");
      cy.visit("/odoo/my-tasks");
      search(lead.task.name);
      cy.contains(".o_data_row", lead.task.name).should("be.visible");
      readTask(lead.task)().should((task) => {
        expect(task.status).to.equal("assigned");
        expect(task.assignee_id[1]).to.equal("Dang Thi Lan");
      });
      cy.readRecord(lead.task, ["assigned_by_id"]).its("assigned_by_id.1").should("eq", "Dang Thi Lan");
      notices(ASSIGNED, lead.task).should(({ messages }) => expect(messages, "claiming notifies nobody").to.be.empty);
    });
  });

  it("TC-WF03-E1 partial lets the head of department move a task to another person, then to another department, with a reason", () => {
    bookedLead().then(({ sample, test, booking }) => {
      const task = { model: "medilab.task", id: booking.task_id[0] };
      step("The head of department moves the task to another person, with a reason");
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
      // The booking returns to the plan, which proposes a slot in the new assignee's working time; the head approves
      // it, and the new assignee is told of the task and of the booking.
      step("The head of department approves the slot the plan proposes for the new assignee");
      openBooking(test, HEAD).should((moved) => {
        expect(moved.person_id[1]).to.equal("Ly Van Hung");
        expect(moved.status).to.equal("proposed");
        expect(moved.calendar_event_id).to.equal(false);
      });
      callAs(HEAD, "medilab.machine.booking", "action_approve", [[booking.id]]);
      openBooking(test, HEAD).should("have.property", "status", "scheduled");
      partnerOf(OTHER_TESTER).then((newTester) => {
        notices(ASSIGNED, task).should(({ partners }) => expect(partners).to.include(newTester));
        notices(APPROVED, booking).should(({ partners }) => expect(partners).to.include(newTester));
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

      // The task leaves the department from the list; the head who moved it still reads it there.
      step("The head moves the task to another department, with a reason");
      cy.visit("/odoo/all-tasks");
      search(sample.code);
      cy.contains(".o_data_row", "Lead (Pb)").find("button[name=action_assign_sample]").click();
      pick("department_id", "Microbiology");
      cy.get(".modal .o_field_widget[name=assignee_id] input").should("have.value", "");
      cy.get(".modal .o_field_widget[name=reason] textarea").clear().type("Only Microbiology can test this sample now.");
      cy.get(".modal button[name=action_confirm]").click();
      cy.get(".modal").should("not.exist");
      cy.contains(".o_data_row", "Lead (Pb)").should("exist");
      readTask(task)().should((read) => {
        expect(read.department_id[1]).to.equal("Microbiology");
        expect(read.status).to.equal("open");
        expect(read.assignee_id).to.equal(false);
      });
      step("The task waits in that department's queue, and its booking and events are gone");
      openBooking(test, ADMINISTRATOR).should("eq", null);
      eventsGone([booking.calendar_event_id[0], ...booking.room_event_ids]);
      readTask(task)().should((read) => {
        expect(read.planned_start).to.equal(false);
        expect(read.planned_end).to.equal(false);
      });
    });
  });

  it("TC-SF10-A2 partial lets the tester cancel a booking, and its slot goes back to the queue", () => {
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
            "Only a scheduled booking can be cancelled.",
          );
          scheduleState(test).should("deep.equal", before);
        });
        // The freed slot is offered again, so the test is recommended a slot that ends no later, which the head approves.
        cy.signInAs("head_of_department");
        cy.openRecord(test);
        cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("be.visible");
        recommendation(test).its("recommended_end").should("be.a", "string").then(time).should("be.at.most", time(booking.ends_at));
        approveThroughScreen();
        openBooking(test).should((replacement) => {
          expect(replacement.id).not.to.equal(booking.id);
          expect(replacement.status).to.equal("scheduled");
          expect(replacement.room_event_ids).to.have.length(1);
        });
      });
    });
  });

  it("TC-WF03-A2 partial creates a machine and step-room booking when the head approves it and keeps them together", () => {
    assignedChromium().then(({ sample, test }) => {
      step("The head of department approves a test with a step in a bookable room");
      cy.signInAs("head_of_department");
      cy.openRecord(test);
      approveThroughScreen();
      cy.signInAs("tester");
      openBooking(test).then((booking) => {
        step("The machine booking holds its room booking, on the tester's calendar");
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
          step("The room booking cannot be removed apart from the machine booking");
          scheduleState(test).then((before) => {
            callRefused("calendar.event", "unlink", [read.room_event_ids]).should("contain", "Move or cancel the machine booking");
            scheduleState(test).should("deep.equal", before);
            callRefused("calendar.event", "write", [read.room_event_ids, { active: false }]).should("contain", "Move or cancel the machine booking");
            scheduleState(test).should("deep.equal", before);
          });
        });
        step("The room booking shows in the room's schedule and the tester's calendar");
        cy.visit("/odoo/location-bookings?view_type=list");
        search(sample.code);
        cy.contains(".o_data_row", sample.code).should("contain", ROOM).and("be.visible");
        cy.visit("/odoo/calendar?view_type=list");
        search(sample.code);
        cy.contains(".o_data_row", ROOM).should("be.visible");
      });
    });
  });

  it("TC-F23-03 rejects a claim from a stale list without changing the winner", () => {
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

  it("TC-F23-03 hides another department's task and refuses its claim over RPC", () => {
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

  it("TC-F23-03 preserves reservations after a missing reason and lets the head retry", () => {
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
        expect(after.bookings[0].status).to.equal("proposed");
        expect(after.events).to.be.empty;
      });
      scheduleState(lead).then((proposed) =>
        callAs(HEAD, "medilab.machine.booking", "action_approve", [[proposed.bookings[0].id]]),
      );
      scheduleState(lead).should((accepted) => expect(accepted.events).to.have.length(2));
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

  it("TC-F24-02 the department plan places due-soon work before other work, then earlier arrivals first", () => {
    saveSettings({ urgency_hours: 12 * 24 });
    assignedChromium({ days: 60 }).then(({ test: ordinary }) =>
      assignedChromium({ days: 12 }).then(({ test: dueSoon }) => {
        openBooking(dueSoon).then((first) =>
          openBooking(ordinary).then((second) => {
            expect([first.status, second.status]).to.deep.equal(["proposed", "proposed"]);
            expect(first.machine_id).to.deep.equal(second.machine_id);
            expect(time(first.ends_at)).to.be.at.most(time(second.starts_at));
            expect(time(first.ends_at) - time(first.starts_at)).to.equal(60 * 60000);
          }),
        );
      }),
    );
    assignedChromium({ days: 60 }).then(({ test: older }) =>
      assignedChromium({ days: 60 }).then(({ test: newer }) => {
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
      callAs(ADMINISTRATOR, "medilab.machine.method", "search_read", [[
        ["machine_id", "=", booking.machine_id[0]],
        ["method_id", "=", booking.method_id[0]],
      ]], {
        fields: ["duration_minutes"],
      }).then(([link]) => {
        expect((time(booking.ends_at) - time(booking.starts_at)) / 60000).to.equal(Math.ceil(link.duration_minutes / 15) * 15);
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
            ["subtype_id.code", "=", REMINDER],
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
          ["mail_message_id.subtype_id.code", "=", REMINDER],
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
          ["subtype_id.code", "=", REMINDER],
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
