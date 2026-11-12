import { callAs, callRefused } from "../../../../support/odoo";
import { newRecord, pick, save } from "../../../../support/form";
import { utcTime } from "../scheduling/calendar";
import { ADMIN, HEAD, TESTER, odooTime, release, schedulingFixture, typeTime } from "../scheduling/setup";

const FIELDS = ["person_id", "starts_at", "ends_at", "reason", "create_uid", "write_date"];

describe("Planned OverTime", () => {
  let fixture;
  let overtime;
  beforeEach(() => {
    fixture = undefined;
    overtime = undefined;
    return schedulingFixture(1, (created) => (fixture = created));
  });
  afterEach(() => {
    if (overtime) callAs(ADMIN, "medilab.overtime", "unlink", [[overtime]]);
    return release(fixture);
  });

  it("TC-F426-1 books a tester in the OverTime their head records, and moving the booking leaves the OverTime", () => {
    const [booking] = fixture.bookings;
    const working = fixture.slots[0];
    // From 20:00 to midnight of the working slot's day where the tester works, after their working hours.
    const day = new Intl.DateTimeFormat("en-CA", { timeZone: fixture.resourceZone }).format(new Date(`${working}Z`));
    const evening = odooTime(utcTime(day, 20, fixture.resourceZone));
    const night = odooTime(utcTime(day, 24, fixture.resourceZone));

    cy.signInAs("tester");
    callRefused("medilab.machine.booking", "write", [[booking], { starts_at: evening }]).should("contain", "is not free");

    cy.signInAs("head_of_department");
    newRecord("/odoo/overtimes");
    pick("person_id", "Dang Thi Lan");
    typeTime(evening, fixture.displayZone);
    typeTime(night, fixture.displayZone, "ends_at");
    cy.get('.o_field_widget[name="reason"] textarea').type("Urgent lead results are due before the internal due date.");
    save();
    cy.location("pathname").then((path) => (overtime = Number(path.split("/").pop())));

    cy.then(() => callAs(ADMIN, "medilab.overtime", "read", [[overtime], FIELDS])).then(([recorded]) => {
      expect(recorded.person_id[0]).to.equal(fixture.tester);
      expect([recorded.starts_at, recorded.ends_at]).to.deep.equal([evening, night]);
      callAs(ADMIN, "medilab.person", "read", [[fixture.head], ["user_id"]]).then(([head]) =>
        expect(recorded.create_uid[0]).to.equal(head.user_id[0]),
      );

      callAs(TESTER, "medilab.machine.booking", "write", [[booking], { starts_at: evening }]);
      callAs(ADMIN, "medilab.machine.booking", "read", [[booking], ["starts_at", "status"]]).then(([moved]) => {
        expect(moved.starts_at).to.equal(evening);
        expect(moved.status).to.equal("scheduled");
      });
      callAs(HEAD, "medilab.machine.booking", "write", [[booking], { starts_at: working }]);
      callAs(ADMIN, "medilab.overtime", "read", [[overtime], FIELDS]).should("deep.equal", [recorded]);
    });
  });
});
