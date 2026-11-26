import { step } from "../../../support/steps";
import { callRefused } from "../../../support/odoo";
import { outsourcedTest, sentDispatch } from "./setup";

describe("F-40 Subcontractor results", () => {
  it("TC-F40-03 shows a subcontractor user only their own dispatches, never a sample's customer", () => {
    sentDispatch("chlorpyrifos").then((other) =>
      sentDispatch().then(({ test, dispatch }) => {
        outsourcedTest().then((draft) => {
          step("The subcontractor sees only its own sent dispatches");
          cy.signInAs("subcontractor");
          cy.visit("/my/dispatches");
          cy.contains("a", dispatch.code).should("be.visible");
          cy.contains("a", other.dispatch.code).should("not.exist");
          cy.contains("a", draft.dispatch.code).should("not.exist");
          cy.request(`/my/dispatches/${draft.dispatch.id}`).should((response) => {
            expect(response.redirects, "sent back to the dispatches").not.to.be.empty;
            expect(response.body).not.to.contain(draft.test.code);
          });
        });
        step("Its dispatch shows the tests, never the sample's customer");
        cy.contains("a", dispatch.code).click();
        cy.contains("tr", test.code).should("contain", "Lead (Pb)");
        cy.get("main").should("not.contain", test.sampleName).and("not.contain", test.customerName);
        cy.request(`/my/dispatches/${other.dispatch.id}`).should((response) => {
          expect(response.redirects, "sent back to the dispatches").not.to.be.empty;
          expect(response.body).not.to.contain(other.test.code);
        });
        callRefused("medilab.sample.test", "read", [[test.id], ["sample_id"]]).should("match", /not allowed to access .*\(medilab\.sample\.test\)/);
      }),
    );
  });
});
