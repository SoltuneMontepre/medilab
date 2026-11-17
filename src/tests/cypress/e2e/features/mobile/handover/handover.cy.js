import { callAs, refAs, signIn } from "../../../../support/odoo";
import { onPhone, signedInPhone } from "../../../../support/mobile";
import { PNG } from "../../../flows/wf-02-sample-reception/setup";

const STAFF = "demo.sample_delivery_staff";

// A new draft handover record of the demo reception request, listing its cabbage handed over short. Yields its id.
function draftRecord() {
  const refs = {};
  refAs(STAFF, "sol_demo.demo_test_request_reception").then(({ id }) => (refs.request = id));
  refAs(STAFF, "sol_demo.demo_sample_reception_insufficient").then(({ id }) => (refs.sample = id));
  refAs(STAFF, "sol_demo.demo_person_sample_delivery_staff").then(({ id }) => (refs.staff = id));
  return cy.then(() =>
    callAs(STAFF, "medilab.handover.record", "create", [
      {
        request_id: refs.request,
        handed_over_by_name: "Trần Văn Bình",
        received_by_id: refs.staff,
        sample_ids: [[0, 0, { sample_id: refs.sample, quantity: "1 small head", condition: "insufficient" }]],
      },
    ]),
  );
}

describe("Medilab Mobile handover record signature on the web", () => {
  it("TC-F520-A1 shows a record the customer signed on the phone as signed on that phone, with its PDF, and read-only", () => {
    draftRecord().then((recordId) => {
      signedInPhone(STAFF).then((key) => {
        onPhone(key, "GET", `/handover-records/${recordId}`).then(({ status, body: draft }) => {
          expect(status).to.eq(200);
          expect(draft.can_sign).to.eq(true);
          expect(draft.samples).to.have.length(1);
        });
        const signature = { signature: PNG, confirmed: true };
        onPhone(key, "POST", `/handover-records/${recordId}/sign`, signature).then(({ status, body: signed }) => {
          expect(status).to.eq(200);
          expect(signed.status).to.eq("signed");
          expect(signed.can_sign).to.eq(false);
          // A signature sent again after a lost answer answers the signed record.
          onPhone(key, "POST", `/handover-records/${recordId}/sign`, signature).its("status").should("eq", 200);

          signIn(STAFF);
          cy.visit(`/odoo/handover-records/${recordId}`);
          cy.get(".o_field_widget[name=status] .o_arrow_button_current").should("contain", "Signed");
          cy.get(".o_field_widget[name=signed_device_id]").should("contain", signed.signed_device);
          cy.get(".o_field_widget[name=attachment_id]").should("contain", `${signed.code}.pdf`);
          cy.get(".o_field_widget[name=handed_over_by_name] input").should("not.exist");
          cy.get(".o_field_widget[name=sample_ids] .o_field_x2many_list_row_add").should("not.exist");
        });
      });
    });
  });
});
