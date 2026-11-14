import { callAs } from "../../../../support/odoo";
import { ADMIN, TESTER, release, schedulingFixture } from "../scheduling/setup";

const RESULT = ["is_interrupted", "interruption_assessment", "booking_id"];

describe("Interrupted results", () => {
  let fixture;
  let resultId;
  beforeEach(() => {
    fixture = undefined;
    resultId = undefined;
    // The tester starts the measurement, then its machine breaks down, which ends the booking.
    return schedulingFixture(1, (created) => (fixture = created))
      .then(() => callAs(TESTER, "medilab.machine.booking", "action_start", [[fixture.bookings[0]]]))
      .then(() => callAs(ADMIN, "medilab.machine", "write", [[fixture.machine], { status: "under_repair" }]))
      .then(() => callAs(ADMIN, "medilab.test.result", "search_read", [[["sample_test_id", "=", fixture.tests[0]]]], { fields: RESULT }))
      .then(([result]) => (resultId = result.id));
  });
  afterEach(() => release(fixture));

  it("TC-F425-1 keeps the data of a machine failure as an interrupted result, which the head assesses", () => {
    callAs(ADMIN, "medilab.machine.booking", "read", [[fixture.bookings[0]], ["status"]]).then(([booking]) => {
      expect(booking.status, "the failure ended the booking").to.equal("done");
    });
    cy.signInAs("tester");
    cy.visit(`/odoo/test-results/${resultId}`);
    cy.get(".o_form_view .alert-warning").should("contain", "The machine stopped during this measurement");
    cy.get('.o_statusbar_buttons button[name="action_assess_usable"]').should("not.exist");

    cy.signInAs("head_of_department");
    cy.visit(`/odoo/test-results/${resultId}`);
    cy.get('.o_statusbar_buttons button[name="action_assess_retest"]').should("be.visible");
    cy.get('.o_statusbar_buttons button[name="action_assess_more_sample"]').should("be.visible");
    cy.get('.o_statusbar_buttons button[name="action_assess_usable"]').click();
    cy.get(".o_form_view .alert-warning").should("contain", "The head of department assessed it").and("contain", "Usable");
    callAs(ADMIN, "medilab.test.result", "read", [[resultId], RESULT]).then(([result]) => {
      expect(result.interruption_assessment).to.equal("usable");
      expect(result.booking_id[0]).to.equal(fixture.bookings[0]);
    });
  });
});
