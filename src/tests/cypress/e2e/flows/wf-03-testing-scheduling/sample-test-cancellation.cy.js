import { callRefused, refAs } from "../../../support/odoo";
import { scheduleState, eventsGone } from "./state";
import { cancellation, openCancelTest } from "./screens";
import {
  ADMINISTRATOR,
  PARAMETERS,
  assign,
  assignedChromium,
  awayFromQuarterHour,
  book,
  receivedSample,
  releaseFixtures,
  resetFixtures,
} from "./setup";

const REASON = "The sample cannot be tested for this parameter.";

beforeEach(() => {
  resetFixtures();
  cy.viewport(1440, 900);
});
afterEach(releaseFixtures);

describe("SF-10 cancelling a sample test", () => {
  it("TC-SF10-A3 partial lets the head cancel a booked test with a reason and ends only its own booking", () => {
    receivedSample([PARAMETERS.chromium, PARAMETERS.ph]).then((sample) => {
      assign(sample);
      const [chromium, ph] = sample.tests;
      awayFromQuarterHour();
      book(chromium).then((booking) =>
        assignedChromium().then(({ test: other }) =>
          book(other).then(() =>
            scheduleState([ph]).then((phBefore) =>
              scheduleState([other]).then((otherBefore) =>
                scheduleState([chromium]).then((before) => {
                  expect(before.bookings[0].status).to.equal("scheduled");
                  cy.signInAs("head_of_department");
                  cy.openRecord(chromium);
                  openCancelTest();
                  // A blank reason is refused on the dialog, which stays open with everything as it was.
                  cy.get(".modal .o_field_widget[name=reason]").should("not.have.class", "o_field_invalid");
                  cy.get(".modal button[name=action_cancel]").click();
                  cy.get(".modal .o_field_widget[name=reason]").should("have.class", "o_field_invalid");
                  scheduleState([chromium]).should("deep.equal", before);

                  cy.get(".modal .o_field_widget[name=reason] textarea").type(REASON);
                  cy.get(".modal button[name=action_cancel]").click();
                  cy.get(".modal").should("not.exist");
                  cy.get(".o_statusbar_buttons")
                    .contains("button", /^Cancel Test$/)
                    .should("not.exist");

                  refAs(ADMINISTRATOR, "sol_demo.demo_person_head_of_department").then((head) =>
                    cancellation(chromium).should((read) => {
                      expect(read.status).to.equal("cancelled");
                      expect(read.cancel_reason).to.equal(REASON);
                      expect(read.cancelled_by_id[0]).to.equal(head.id);
                      expect(read.cancelled_at).to.be.a("string");
                    }),
                  );
                  scheduleState([chromium]).should((after) => {
                    expect(after.tasks[0].status).to.equal("cancelled");
                    expect(after.tasks[0].planned_start).to.equal(false);
                    expect(after.tasks[0].planned_end).to.equal(false);
                    expect(after.bookings).to.have.length(1);
                    expect(after.bookings[0].status).to.equal("cancelled");
                    expect(after.bookings[0].calendar_event_id).to.equal(false);
                    expect(after.bookings[0].room_event_ids).to.be.empty;
                    expect(after.events).to.be.empty;
                  });
                  eventsGone([booking.calendar_event_id[0], ...booking.room_event_ids]);

                  // Only this test and its booking end: the sample's other test and another test's booking keep every field.
                  scheduleState([ph]).should("deep.equal", phBefore);
                  scheduleState([other]).should("deep.equal", otherBefore);
                }),
              ),
            ),
          ),
        ),
      );
    });
  });

  it("TC-SF10-A3 partial keeps the Cancel Test action from a tester and refuses it over RPC", () => {
    assignedChromium().then(({ test }) => {
      cy.signInAs("tester");
      cy.openRecord(test);
      cy.get(".o_statusbar_buttons").should("be.visible").and("contain", "Schedule");
      cy.contains(".o_statusbar_buttons button", /^Cancel Test$/).should("not.exist");
      scheduleState([test]).then((before) => {
        callRefused("medilab.sample.test", "action_cancel", [[test.id], REASON]).should("match", /not allowed|access/i);
        scheduleState([test]).should("deep.equal", before);
        expect(before.tests[0].status).to.equal("assigned");
      });
    });
  });
});
