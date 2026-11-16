import { callAs, callRefused } from "../../../../support/odoo";
import { LAB_HEAD, REPORT, STAFF, draftReport, personNames } from "../../../flows/wf-06-report-release/setup";

describe("Document locking (F-44)", () => {
  it("TC-F44-01 shows who holds the lock of a document another user is editing, and still lets others read it", () => {
    draftReport().then(({ request }) => {
      callAs(STAFF, "medilab.test.request", "lock_take", [[request.id]])
        .its("taken")
        .should("eq", true);
      cy.signInAs("administrator");
      cy.openRecord(request);
      personNames("sol_demo.demo_person_sample_delivery_staff").then(([staff]) => cy.contains(".o_form_view", "is editing").should("contain", staff));
      cy.get(".o_field_widget[name=customer_id] input").invoke("val").should("contain", "Nước Uống Sạch");
      callAs(STAFF, "medilab.test.request", "lock_release", [[request.id], "left"]);
    });
  });

  it("TC-F44-03 keeps a signed document read-only for everyone, administrators included", () => {
    draftReport().then(({ report }) =>
      callAs(LAB_HEAD, REPORT, "read", [[report.id], ["result_ids"]]).then(([read]) => {
        cy.signInAs("administrator");
        callRefused("medilab.test.result", "write", [[read.result_ids[0]], { value: 1 }]).should(
          "eq",
          "The document has signatures; withdraw them before changing it.",
        );
      }),
    );
  });
});
