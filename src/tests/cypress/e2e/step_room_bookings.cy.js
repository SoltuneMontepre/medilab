import { call, signIn } from "../support/odoo";

const ROOM = "Sample preparation room";

// The id of a demo record.
function demoId(xmlId) {
  return call("ir.model.data", "check_object_reference", ["sol_demo", xmlId]).then(([, id]) => id);
}

describe("Room bookings of method steps", () => {
  beforeEach(() => signIn("demo.tester"));

  it("shows the room booking of a scheduled test on its booking and the tester's calendar", () => {
    demoId("demo_machine_booking_lead_room_booked").then((bookingId) => {
      cy.visit(`/odoo/machine-schedule/${bookingId}`);
      cy.get(".o_notebook a[name=room_bookings]").click();
      cy.contains(".o_field_widget[name=room_event_ids] .o_data_row", ROOM).should("be.visible");

      call("medilab.machine.booking", "read", [[bookingId], ["room_event_ids"]]).then(([booking]) =>
        call("calendar.event", "read", [booking.room_event_ids, ["partner_ids", "location_id"]]).then((events) => {
          expect(events).to.have.length(1);
          expect(events[0].location_id[1]).to.contain(ROOM);
        }),
      );
    });
  });

  it("refuses moving a room booking apart from its machine booking", () => {
    demoId("demo_machine_booking_lead_room_booked").then((bookingId) =>
      call("medilab.machine.booking", "read", [[bookingId], ["room_event_ids"]]).then(([booking]) =>
        cy
          .request("POST", "/web/dataset/call_kw/calendar.event/unlink", {
            jsonrpc: "2.0",
            method: "call",
            params: { model: "calendar.event", method: "unlink", args: [booking.room_event_ids], kwargs: {} },
          })
          .its("body.error.data.message")
          .should("contain", "Move or cancel the machine booking"),
      ),
    );
  });
});
