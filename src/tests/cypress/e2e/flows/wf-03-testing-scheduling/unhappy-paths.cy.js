import { callAs, callRefused, refAs } from "../../../support/odoo";
import { pick, search } from "../../../support/form";
import { scheduleState, eventsGone } from "./state";
import {
  HEAD,
  TESTER,
  PARAMETERS,
  PEOPLE,
  assign,
  assignedChromium,
  book,
  openBooking,
  receivedSample,
  resetFixtures,
  releaseFixtures,
  scheduleThroughScreen,
} from "./setup";

beforeEach(() => {
  resetFixtures();
  cy.viewport(1440, 900);
});
afterEach(releaseFixtures);

describe("WF-03 current permission and validation boundaries", () => {
  it("TC-F23-03 RPC refuses reassignment by a tester and leaves all reservations with their owner", () => {
    assignedChromium().then(({ sample, test }) => {
      book(test);
      cy.signInAs("tester");
      scheduleState(test).then((before) =>
        refAs(HEAD, PEOPLE.chemistryTester).then(({ id }) => {
          callRefused("medilab.task", "write", [
            [test.task.id],
            {
              assignee_id: id,
              reassign_reason: "A colleague is available.",
            },
          ]).should("contain", "You are not allowed to");
          scheduleState(test).should("deep.equal", before);
        }),
      );
      cy.visit("/odoo/my-tasks");
      search(sample.code);
      cy.contains(".o_data_row", test.task.name).should("be.visible");
    });
  });

  it("TC-F24-03 RPC refuses another tester's scheduling and allows the assignee to use Schedule", () => {
    assignedChromium().then(({ test }) => {
      cy.signInAs("chemistry_tester");
      scheduleState(test).then((before) => {
        callRefused("medilab.sample.test", "action_schedule", [[test.id]]).should("match", /not allowed|access/i);
        scheduleState(test).should("deep.equal", before);
      });
      cy.signInAs("tester");
      cy.openRecord(test);
      scheduleThroughScreen();
      openBooking(test).then((booking) => {
        expect(booking.status).to.equal("scheduled");
        cy.signInAs("chemistry_tester");
        scheduleState(test).then((before) => {
          const later = new Date(Date.parse(`${booking.starts_at}Z`) + 3600000).toISOString().slice(0, 19).replace("T", " ");
          callRefused("medilab.machine.booking", "write", [[booking.id], { starts_at: later }]).should("contain", "doesn't have 'read' access");
          scheduleState(test).should("deep.equal", before);
          callRefused("medilab.machine.booking", "action_cancel", [[booking.id]]).should("contain", "doesn't have 'read' access");
          scheduleState(test).should("deep.equal", before);
        });
      });
    });
  });

  it("TC-F24-03 RPC refuses an unassigned test and a duplicate Schedule without creating extra events", () => {
    receivedSample([PARAMETERS.chromium]).then((sample) => {
      const [test] = sample.tests;
      cy.signInAs("tester");
      scheduleState(test).then((before) => {
        callRefused("medilab.sample.test", "action_schedule", [[test.id]]).should("match", /^Assign .+ to a person before scheduling it\.$/);
        scheduleState(test).should("deep.equal", before);
      });
      assign(sample);
      cy.openRecord(test);
      scheduleThroughScreen();
      openBooking(test).should("have.property", "status", "scheduled");
      scheduleState(test).then((before) => {
        callRefused("medilab.sample.test", "action_schedule", [[test.id]]).should("match", /is already waiting for or holding a machine\.$/);
        scheduleState(test).should("deep.equal", before);
        expect(before.bookings).to.have.length(1);
        expect(before.events).to.have.length(2);
      });
    });
  });

  it("TC-F24-03 baseline hides Schedule when no machine can finish before the due date and refuses RPC", () => {
    assignedChromium({ days: 0 }).then(({ test }) => {
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(".o_statusbar_buttons button[name=action_schedule]").should("not.exist");
      scheduleState(test).then((before) => {
        callRefused("medilab.sample.test", "action_schedule", [[test.id]]).should("match", /^No machine can finish .+ before its due date\.$/);
        scheduleState(test).should("deep.equal", before);
        expect(before.bookings).to.be.empty;
        expect(before.events).to.be.empty;
      });
    });
  });

  it("TC-F23-03 keeps a booked task unchanged without a department-transfer reason and permits retry", () => {
    assignedChromium().then(({ sample, test }) =>
      book(test).then((booking) => {
        cy.signInAs("head_of_department");
        cy.visit("/odoo/all-tasks");
        search(sample.code);
        cy.contains(".o_data_row", test.task.name).find("button[name=action_assign_sample]").click();
        pick("department_id", "Microbiology");
        scheduleState(test).then((before) => {
          cy.get(".modal button[name=action_confirm]").click();
          cy.get(".modal .o_field_widget[name=reason]").should("have.class", "o_field_invalid");
          scheduleState(test).should("deep.equal", before);
          refAs(HEAD, "sol_demo.demo_hr_department_microbiology").then(({ id }) => {
            callRefused("medilab.task", "write", [[test.task.id], { department_id: id, assignee_id: false }]).should(
              "match",
              /^Give a reason for moving .+ to another person or department\.$/,
            );
            scheduleState(test).should("deep.equal", before);
          });
        });
        cy.get(".modal .o_field_widget[name=reason] textarea").type("Microbiology will take over this sample.");
        cy.get(".modal button[name=action_confirm]").click();
        cy.get(".modal").should("not.exist");
        scheduleState(test).should((after) => {
          expect(after.tasks[0].department_id[1]).to.equal("Microbiology");
          expect(after.tasks[0].status).to.equal("open");
          expect(after.tasks[0].assignee_id).to.equal(false);
          expect(after.tasks[0].planned_start).to.equal(false);
          expect(after.tasks[0].planned_end).to.equal(false);
          expect(after.bookings[0].status).to.equal("cancelled");
          expect(after.events).to.be.empty;
        });
        eventsGone([booking.calendar_event_id[0], ...booking.room_event_ids]);
      }),
    );
  });

  it("TC-F24-03 rejects Start from a stale cancelled booking form and lets the tester book again", () => {
    assignedChromium().then(({ test }) =>
      book(test).then((booking) => {
        cy.signInAs("tester");
        cy.visit(`/odoo/machine-schedule/${booking.id}`);
        cy.get(".o_statusbar_buttons button[name=action_start]").should("be.visible");
        callAs(TESTER, "medilab.machine.booking", "action_cancel", [[booking.id]]);
        cy.expectRefusal({
          read: () => scheduleState(test),
          action: () => cy.get(".o_statusbar_buttons button[name=action_start]").click(),
          message: "Only a scheduled booking can be started.",
        });
        cy.reload();
        cy.get(".o_statusbar_buttons button[name=action_start]").should("not.exist");
        eventsGone([booking.calendar_event_id[0], ...booking.room_event_ids]);
        cy.openRecord(test);
        scheduleThroughScreen();
        openBooking(test).should((replacement) => {
          expect(replacement.id).not.to.equal(booking.id);
          expect(replacement.status).to.equal("scheduled");
        });
      }),
    );
  });
});
