import { callAs } from "../../../../support/odoo";
import { save } from "../../../../support/form";
import { TESTER, release, schedulingFixture, snapshot, typeStart } from "../scheduling/setup";

const BOOKING = ["status", "machine_id", "starts_at", "ends_at"];

describe("Shared machine intervals", () => {
  let fixture;
  beforeEach(() => {
    fixture = undefined;
    // Three samples of one method on a machine that holds two samples in one interval.
    return schedulingFixture(3, (created) => (fixture = created), 2);
  });
  afterEach(() => release(fixture));

  it("TC-F420-1 lets the tester join another sample's interval of the same method, which books its room once", () => {
    snapshot(fixture).then((before) => {
      const [holder, joiner] = before.bookings;
      cy.signInAs("tester");
      cy.visit(`/odoo/machine-schedule/${joiner.id}`);
      typeStart(holder.starts_at, fixture.displayZone);
      cy.intercept("POST", "/web/dataset/call_kw/medilab.machine.booking/web_save").as("savedBooking");
      save();
      cy.wait("@savedBooking").its("response.body.error").should("not.exist");
      snapshot(fixture).then((after) => {
        const joined = after.bookings.find((row) => row.id === joiner.id);
        const held = after.bookings.find((row) => row.id === holder.id);
        expect(Cypress._.pick(joined, BOOKING)).to.deep.equal(Cypress._.pick(holder, BOOKING));
        expect(held).to.deep.equal(holder);
        expect(joined.room_event_ids, "the room is booked once, by the holder").to.be.empty;
        expect(after.events.filter((event) => event.location_id && event.active)).to.have.length(
          before.events.filter((event) => event.location_id && event.active).length - 1,
        );
      });
    });
  });

  it("TC-F420-2 refuses a third sample once the interval holds two", () => {
    snapshot(fixture).then((before) => {
      const [holder, joiner, third] = before.bookings;
      callAs(TESTER, "medilab.machine.booking", "write", [[joiner.id], { starts_at: holder.starts_at }]);
      cy.signInAs("tester");
      cy.visit(`/odoo/machine-schedule/${third.id}`);
      typeStart(holder.starts_at, fixture.displayZone);
      cy.expectRefusal({
        read: () => snapshot(fixture),
        action: () => cy.get(".o_form_button_save").click(),
        message: `${third.machine_id[1]} is not free`,
      });
    });
  });
});
